"""create initial tables

Revision ID: 0001
Revises: 
Create Date: 2024-07-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=False),
        sa.Column('hashed_password', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'repository_uploads',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column('repo_path', sa.Text(), nullable=False),
        sa.Column('upload_time', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'analysis_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('upload_id', sa.Integer(), sa.ForeignKey("repository_uploads.id"), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('commit_message', sa.Text(), nullable=True),
        sa.Column('code_suggestions', sa.JSON(), nullable=True),
        sa.Column('detected_issues', sa.JSON(), nullable=True),
        sa.Column('raw_llm_response', sa.JSON(), nullable=True),
    )

def downgrade():
    op.drop_table('analysis_results')
    op.drop_table('repository_uploads')
    op.drop_table('sessions')
    op.drop_table('users')
