"""Sprint 5.3: re-encriptação de tokens OAuth como CLI (fora do boot)."""

from sqlalchemy import text

from models import User, db
from scripts.migrations.encrypt_oauth_tokens import encrypt_pending_oauth_tokens
from services.token_crypto import decrypt_value, encrypt_value, looks_like_fernet


def _criar_conexao(user_id: int, access: str | None, refresh: str) -> int:
    # SQL cru: o TypeDecorator EncryptedText encriptaria na escrita via ORM,
    # e o alvo do teste é justamente o dado plaintext em repouso.
    db.session.execute(
        text(
            "INSERT INTO user_calendar_connection "
            "(user_id, provider, calendar_id, access_token, refresh_token, "
            "created_at, updated_at) "
            "VALUES (:uid, 'google', 'primary', :access, :refresh, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"uid": user_id, "access": access, "refresh": refresh},
    )
    db.session.commit()
    return db.session.execute(
        text("SELECT MAX(id) FROM user_calendar_connection")
    ).scalar()


def _tokens_em_repouso(conn_id: int) -> tuple[str | None, str]:
    return db.session.execute(
        text(
            "SELECT access_token, refresh_token FROM user_calendar_connection "
            "WHERE id = :cid"
        ),
        {"cid": conn_id},
    ).one()


def _criar_usuario(username: str) -> User:
    user = User(username=username, name=username, orgao="Orgao Teste")
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    return user


def test_dry_run_conta_pendentes_sem_gravar(app):
    with app.app_context():
        user = _criar_usuario("dono")
        conn_id = _criar_conexao(user.id, "token-plano", "refresh-plano")

        stats = encrypt_pending_oauth_tokens(apply=False)
        db.session.commit()

        assert stats == {"rows_scanned": 1, "rows_pending": 1, "rows_encrypted": 0}
        access, refresh = _tokens_em_repouso(conn_id)
        assert access == "token-plano"
        assert refresh == "refresh-plano"


def test_apply_encripta_apenas_plaintext(app):
    with app.app_context():
        user = _criar_usuario("dono")
        outro = _criar_usuario("outro")
        plain_id = _criar_conexao(user.id, "token-plano", "refresh-plano")
        ja_encriptado = encrypt_value("refresh-seguro")
        cifrado_id = _criar_conexao(outro.id, None, ja_encriptado)

        stats = encrypt_pending_oauth_tokens(apply=True)
        db.session.commit()

        assert stats["rows_scanned"] == 2
        assert stats["rows_encrypted"] == 1
        access, refresh = _tokens_em_repouso(plain_id)
        assert looks_like_fernet(access) and looks_like_fernet(refresh)
        assert decrypt_value(access) == "token-plano"
        assert decrypt_value(refresh) == "refresh-plano"
        # Linha já cifrada permanece intocada (idempotência).
        _, refresh_intocado = _tokens_em_repouso(cifrado_id)
        assert refresh_intocado == ja_encriptado


def test_reexecucao_e_noop(app):
    with app.app_context():
        user = _criar_usuario("dono")
        _criar_conexao(user.id, "token-plano", "refresh-plano")
        encrypt_pending_oauth_tokens(apply=True)
        db.session.commit()

        stats = encrypt_pending_oauth_tokens(apply=True)
        assert stats["rows_pending"] == 0
        assert stats["rows_encrypted"] == 0
