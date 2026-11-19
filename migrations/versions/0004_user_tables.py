"""Add member tables: users, user_profiles, user_consents, checkin_responses.

로그인 방식과 상관없는 회원 테이블만 만든다. 로그인 수단(user_identities)·세션(auth_sessions)은
방식이 정해지면 다음 revision 에서 추가한다 (계획: app/users/models.py 주석, docs/DATABASE.md).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('active', 'withdrawn')", name=op.f('ck_users_status')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_table('checkin_responses',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('question_version', sa.String(length=30), nullable=False),
    sa.Column('answers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('completed', sa.Boolean(), nullable=False),
    sa.Column('source', sa.String(length=10), server_default='survey', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('survey', 'chat')", name=op.f('ck_checkin_responses_source')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_checkin_responses_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_checkin_responses'))
    )
    op.create_index('ix_checkin_responses_user_id_created_at', 'checkin_responses', ['user_id', 'created_at'], unique=False)
    op.create_table('user_consents',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('consent_type', sa.String(length=30), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('agreed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("consent_type IN ('terms', 'privacy', 'sensitive_info', 'checkin_storage', 'chat_history')", name=op.f('ck_user_consents_consent_type')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_consents_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_consents'))
    )
    op.create_index('ix_user_consents_user_id_consent_type', 'user_consents', ['user_id', 'consent_type'], unique=False)
    op.create_table('user_profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('birth_year', sa.SmallInteger(), nullable=True),
    sa.Column('sex', sa.String(length=2), nullable=True),
    sa.Column('sigungu_cd', sa.String(length=5), nullable=True),
    sa.Column('job', sa.String(length=20), nullable=True),
    sa.Column('school', sa.String(length=20), nullable=True),
    sa.Column('situations', postgresql.ARRAY(sa.String(length=20)), server_default=sa.text("'{}'::varchar[]"), nullable=False),
    sa.Column('interests', postgresql.ARRAY(sa.String(length=20)), server_default=sa.text("'{}'::varchar[]"), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("sex IS NULL OR sex IN ('남', '여')", name=op.f('ck_user_profiles_sex')),
    sa.CheckConstraint("sigungu_cd IS NULL OR sigungu_cd ~ '^[0-9]{5}$'", name=op.f('ck_user_profiles_sigungu_cd')),
    sa.CheckConstraint('birth_year IS NULL OR birth_year BETWEEN 1900 AND 2100', name=op.f('ck_user_profiles_birth_year')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_user_profiles'))
    )


def downgrade() -> None:
    op.drop_table('user_profiles')
    op.drop_index('ix_user_consents_user_id_consent_type', table_name='user_consents')
    op.drop_table('user_consents')
    op.drop_index('ix_checkin_responses_user_id_created_at', table_name='checkin_responses')
    op.drop_table('checkin_responses')
    op.drop_table('users')
