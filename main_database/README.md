# main_database

This service provides the persistent database for the CodeReview Assistant application.

## Models

- **User**: Stores registered user information.
- **Session**: Tracks user session tokens.
- **RepositoryUpload**: Stores each uploaded/analyzed repository event.
- **AnalysisResult**: Stores LLM/code review, generated messages, and optimization outputs.

## Migrations

To create or update migration scripts, use Alembic.

## Setup & Usage

- Uses SQLAlchemy ORM and Alembic for migrations.
- Env variables required for database connectivity are read from the `.env` file (see `alembic.ini` and `db.py`).

## Directory Structure

- `models.py`: SQLAlchemy ORM model definitions.
- `db.py`: Database engine, session, and utilities.
- `alembic/`: Migration scripts and Alembic env.
