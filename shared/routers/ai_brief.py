"""AI Brief API — cross-app endpoint cho chat widget của 7 app.

Mounted at /api/ai-brief trong: baogia, marketing, muahang, hcns, ketoan,
saleadmin, ceo.

Endpoints:
  GET  /api/ai-brief                → Brief hôm nay của user đang đăng nhập
                                       (auto-generate nếu chưa có)
  POST /api/ai-brief/read           → Đánh dấu đã đọc + tăng opened_count
  POST /api/ai-brief/regenerate     → Re-gen brief hôm nay (admin/dev only)
  POST /api/ai-brief/generate-all   → Cron 6h sáng gen cho mọi user (admin/cron)
"""
from __future__ import annotations

import re
from datetime import date as _date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.db import get_db


router = APIRouter()
_AUTH = Depends(current_user)

_CEO_ROLES = frozenset({"admin", "ceo", "assistant_ceo"})


def _lazy_service():
    """Lazy import — service nằm ở ceo app nhưng router shared dùng được.

    Khi run app NON-CEO mà service chưa import được → log + raise 503.
    """
    from ceo.app.ai_brief import service as _svc
    return _svc


@router.get("")
def get_brief_today(
    date_iso: Optional[str] = Query(None, description="YYYY-MM-DD, default today"),
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """Lấy brief hôm nay (hoặc ngày chỉ định) của user đang đăng nhập.

    Nếu chưa có → tự sinh ngay (LLM call có thể tốn 2-3s).
    """
    try:
        brief_date = _date.fromisoformat(date_iso) if date_iso else _date.today()
    except Exception:
        brief_date = _date.today()

    svc = _lazy_service()
    brief = svc.generate_brief_for_user(
        db,
        user_id=user.sub,
        username=user.username,
        role=user.role,
        brief_date=brief_date,
        force=False,
    )
    return {
        "id": brief.id,
        "date": brief.brief_date.isoformat(),
        "level": brief.brief_level,
        "ho_ten": brief.ho_ten,
        "phong_ban": brief.phong_ban,
        "content_md": brief.content_md,
        "metrics": brief.metrics,
        "alerts": brief.alerts,
        "highlights": brief.highlights,
        "model_used": brief.model_used,
        "generated_at": brief.generated_at.isoformat() if brief.generated_at else None,
        "read_at": brief.read_at.isoformat() if brief.read_at else None,
        "opened_count": brief.opened_count,
    }


@router.post("/read")
def mark_brief_read(
    date_iso: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """Đánh dấu user đã mở brief hôm nay."""
    try:
        brief_date = _date.fromisoformat(date_iso) if date_iso else _date.today()
    except Exception:
        brief_date = _date.today()

    from ceo.app.ai_brief import store
    store.mark_read(db, user.sub, brief_date)
    return {"ok": True}


@router.post("/regenerate")
def regenerate_brief(
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """Re-gen brief hôm nay cho chính user (force = True).

    Cho phép user tự refresh nếu cảm thấy brief cũ. Cost ~1 LLM call.
    """
    svc = _lazy_service()
    brief = svc.generate_brief_for_user(
        db,
        user_id=user.sub,
        username=user.username,
        role=user.role,
        brief_date=_date.today(),
        force=True,
    )
    return {
        "ok": True,
        "id": brief.id,
        "content_md": brief.content_md,
        "model_used": brief.model_used,
        "cost_usd": float(brief.cost_usd or 0),
    }


@router.post("/generate-all")
def generate_all(
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """Admin/cron trigger — gen brief cho mọi user active."""
    if (user.role or "").lower() not in _CEO_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/CEO chạy được")
    svc = _lazy_service()
    summary = svc.generate_briefs_for_all(db)
    return summary


# ─── Chat 2 chiều với Mai ────────────────────────────────────────────

class ChatSendIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


def _lazy_chat_service():
    from ceo.app.ai_brief import chat_service as _cs
    return _cs


@router.get("/chat/history")
def chat_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """Lịch sử chat của user đang đăng nhập với Mai (oldest → newest)."""
    cs = _lazy_chat_service()
    msgs = cs.list_history(db, user_id=user.sub, limit=limit)
    return {
        "user": {"id": user.sub, "username": user.username},
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "model_used": m.model_used,
            }
            for m in msgs
        ],
    }


@router.post("/chat/send")
def chat_send(
    body: ChatSendIn,
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """User gửi 1 câu → Mai trả lời ngay (sync, ~2-5s)."""
    cs = _lazy_chat_service()
    try:
        return cs.send_message(
            db,
            user_id=user.sub,
            username=user.username,
            role=user.role,
            user_message=body.message,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except RuntimeError as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e))


# ─── Gọi Mai (thoại 2 chiều) — SSE streaming ────────────────────────

# Lọc emoji + ký hiệu trang trí trước khi đọc TTS (FPT không đọc icon).
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F"
    "\U0000200D\U00002764\U00002122\U00002139\U000024C2]+",
    flags=re.UNICODE,
)
_MD_RE = re.compile(r"[*_`#>~|]+")


def _clean_for_tts(text: str) -> str:
    t = _EMOJI_RE.sub("", text or "")
    t = _MD_RE.sub("", t)
    t = t.replace("—", ", ").replace("–", ", ").replace("•", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


class VoiceTurnIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


def _stt_transcribe_sync(audio: UploadFile):
    """Gửi audio (mp4/aac iOS, webm/opus Chrome) tới STT container (faster-whisper).
    Trả (text, status) với status ∈ {ok, empty, busy, error}:
      - busy: STT đang xử lý lượt khác (503) -> frontend bỏ qua, nghe tiếp.
      - empty: không nghe ra chữ nào.  - error: lỗi mạng/timeout."""
    import os
    import logging as _lg
    import httpx
    stt_url = os.getenv("STT_URL", "http://stt:8009").rstrip("/")
    try:
        data = audio.file.read()
    except Exception:
        data = b""
    if not data:
        return "", "empty"
    files = {"audio": (audio.filename or "rec.webm", data,
                       audio.content_type or "application/octet-stream")}
    try:
        # STT serialize 1 request/lần (~4s). connect nhanh, read rộng cho lúc CPU tải cao.
        # 2026-06-27: nới read 25→40s vì whisper chậm thất thường khi CPU bị giành (tránh báo im).
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=40.0, write=10.0, pool=5.0)) as cli:
            r = cli.post(stt_url + "/transcribe", files=files)
        if r.status_code == 503:
            return "", "busy"
        r.raise_for_status()
        return (r.json().get("text") or "").strip(), "ok"
    except Exception as e:  # noqa: BLE001
        _lg.getLogger(__name__).warning("STT transcribe failed: %s", e)
        return "", "error"


@router.post("/voice/turn-audio")
def voice_turn_audio(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """1 lượt thoại từ AUDIO (iPhone/mọi trình duyệt): ghi âm -> STT(server) -> Mai.
    Nhận multipart 'audio', trả SSE Y HỆT /voice/turn."""
    import json as _json
    text, status = _stt_transcribe_sync(audio)
    if status != "ok" or not text:
        # busy/empty/error -> phát tín hiệu NHẸ (frontend nghe lại im lặng, KHÔNG báo lỗi
        # ồn ào). 'busy' = STT đang bận lượt khác; 'noinput' = không nghe ra chữ.
        sig = "busy" if status == "busy" else "noinput"

        def _skip():
            yield ("data: " + _json.dumps({"type": sig}, ensure_ascii=False) + "\n\n")
            yield ("data: " + _json.dumps(
                {"type": "done", "cost_usd": 0.0}, ensure_ascii=False) + "\n\n")
        return StreamingResponse(
            _skip(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    # Tái dùng nguyên pipeline text (LLM + TTS streaming) của /voice/turn.
    return voice_turn(VoiceTurnIn(message=text), db=db, user=user)


@router.post("/voice/turn")
def voice_turn(
    body: VoiceTurnIn,
    db: Session = Depends(get_db),
    user: JWTPayload = _AUTH,
):
    """1 lượt thoại với Mai: nhận câu anh vừa nói (đã STT ở browser) →
    stream text deltas + audio MP3 (base64) qua SSE.

    Hợp đồng sự kiện (frontend phụ thuộc — mỗi sự kiện 1 dòng `data: <json>\\n\\n`):
      {"type":"thinking"}
      {"type":"text","delta":"..."}
      {"type":"audio","seq":N,"mime":"audio/mpeg","b64":"<base64 mp3>"}
      {"type":"done","cost_usd":<float>}
      {"type":"error","message":"..."}

    Audio phát NGAY khi câu đầu xong (split_sentences), không chờ hết. Quota
    riêng cho voice (không để quota chat-text 50/ngày cắt giữa cuộc gọi).
    """
    import json as _json

    cs = _lazy_chat_service()

    # Chuẩn bị input + quota TRƯỚC khi mở stream (lỗi sớm → trả HTTP code đúng,
    # không vỡ giữa SSE).
    user_message = (body.message or "").strip()
    if not user_message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message rỗng")
    if len(user_message) > 2000:
        user_message = user_message[:2000]

    voice_count = cs._count_voice_today(db, user.sub)
    if voice_count >= cs._VOICE_DAILY_LIMIT:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Bạn đã gọi Mai {cs._VOICE_DAILY_LIMIT} lượt hôm nay. "
            f"Quota reset 00:00 mai để kiểm soát chi phí.",
        )

    # Cấu hình giọng (fallback an toàn nếu module config chưa có).
    try:
        from ceo.app.ai_brief.voice_config import get_voice_config
        cfg = get_voice_config()
    except Exception:
        cfg = {"enabled": True, "voice": None, "speed": None}

    # Resolve thông tin NV + level + snapshot + history (tái dùng helper sẵn có).
    emp = cs._lookup_employee(db, user.username)
    level = cs._decide_level(emp.get("role") or user.role)
    ho_ten = emp.get("ho_ten") or user.username
    phong_ban = emp.get("phong_ban")

    # Lưu user_msg TRƯỚC (đánh dấu nguồn voice để đếm quota riêng).
    user_msg = cs._save_message(
        db,
        user_id=user.sub, username=user.username,
        role="user", content=user_message,
        brief_level=cs._VOICE_LEVEL_TAG,
    )

    snapshot = cs._build_context_snapshot(
        db, level=level, username=user.username, ho_ten=ho_ten,
        role=user.role, phong_ban=phong_ban,
    )
    history = cs.list_history(db, user.sub, limit=cs._HISTORY_LIMIT)
    history = [m for m in history if m.id != user_msg.id]

    def _sse(obj: dict) -> str:
        return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"

    def _gen():
        import asyncio
        import base64
        from shared.services.tts import synthesize, split_sentences, TTSError

        yield _sse({"type": "thinking"})

        voice_enabled = bool(cfg.get("enabled", True))
        voice = cfg.get("voice")
        speed = cfg.get("speed")

        full_text_parts: list[str] = []
        pending = ""          # text tích luỹ chưa tách thành câu phát audio
        audio_seq = 0
        usage: dict = {}
        tts_failed = False    # đã báo lỗi TTS 1 lần → thôi cố synth nữa

        def _synth_mp3(sentence: str) -> bytes:
            # Chạy synthesize (async) an toàn dù thread đã có event loop hay chưa.
            try:
                asyncio.get_running_loop()
                running = True
            except RuntimeError:
                running = False
            if not running:
                return asyncio.run(synthesize(sentence, voice=voice, speed=speed))
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(
                    lambda: asyncio.run(synthesize(sentence, voice=voice, speed=speed))
                ).result()

        def _emit_audio(sentence: str):
            """Synth 1 câu → trả list event (audio hoặc error). Graceful."""
            nonlocal audio_seq, tts_failed
            events: list[str] = []
            if not voice_enabled or tts_failed or not sentence.strip():
                return events
            try:
                clean = _clean_for_tts(sentence)
                if not clean:
                    return events
                mp3 = _synth_mp3(clean)
                print(f"[voice] TTS ok seq={audio_seq} bytes={len(mp3)} sent={clean[:30]!r}", flush=True)
                b64 = base64.b64encode(mp3).decode("ascii")
                events.append(_sse({
                    "type": "audio", "seq": audio_seq,
                    "mime": "audio/mpeg", "b64": b64,
                }))
                audio_seq += 1
            except TTSError as te:
                # Thiếu key / lỗi TTS → báo 1 event error nhưng VẪN stream text.
                tts_failed = True
                print(f"[voice] TTS TTSError: {te}", flush=True)
                events.append(_sse({
                    "type": "error",
                    "message": f"Lỗi tổng hợp giọng: {te}",
                }))
            except Exception as ee:
                tts_failed = True
                import traceback
                traceback.print_exc()
                print(f"[voice] TTS EXC {type(ee).__name__}: {ee}", flush=True)
                events.append(_sse({
                    "type": "error",
                    "message": f"Lỗi tổng hợp giọng: {type(ee).__name__}",
                }))
            return events

        try:
            for kind, payload in cs._call_chat_llm_stream(
                db=db, user_id=user.sub, username=user.username,
                ho_ten=ho_ten, level=level, phong_ban=phong_ban,
                snapshot=snapshot, history=history, user_message=user_message,
            ):
                if kind == "text":
                    full_text_parts.append(payload)
                    yield _sse({"type": "text", "delta": payload})
                    # Phát audio NGAY khi 1 câu hoàn chỉnh (giảm độ trễ tới tiếng đầu).
                    pending += payload
                    sentences = split_sentences(pending)
                    if len(sentences) > 1:
                        for s in sentences[:-1]:
                            for ev in _emit_audio(s):
                                yield ev
                        pending = sentences[-1]
                elif kind == "error":
                    yield _sse({"type": "error", "message": payload})
                elif kind == "usage":
                    usage = payload or {}

            # Phát nốt phần còn lại trong buffer.
            for s in split_sentences(pending):
                for ev in _emit_audio(s):
                    yield ev

            # Lưu assistant_msg (tái dùng _save_message như send_message).
            content_md = "".join(full_text_parts).strip()
            if content_md:
                cs._save_message(
                    db,
                    user_id=user.sub, username=user.username,
                    role="assistant", content=content_md,
                    brief_level=cs._VOICE_LEVEL_TAG,
                    model_used=usage.get("model"),
                    tokens_in=usage.get("tokens_in", 0),
                    tokens_out=usage.get("tokens_out", 0),
                    cost_usd=usage.get("cost_usd", 0.0),
                )

            yield _sse({"type": "done", "cost_usd": float(usage.get("cost_usd", 0.0))})
        except Exception as e:  # noqa: BLE001 — không để vỡ SSE giữa chừng
            yield _sse({"type": "error", "message": f"{type(e).__name__}"})
            yield _sse({"type": "done", "cost_usd": float(usage.get("cost_usd", 0.0))})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
