"""
Tests for the pipeline repository layer.

Uses SQLite in-memory database for fast testing.
"""
import pytest
import asyncio
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from config.database import Base, get_db, get_async_db
from pipeline.models_database import (
    PipelineRunDB,
    AgentResultDB,
    CheckpointDB,
    JobDB,
)
from pipeline.repository import (
    PipelineRepository,
    AsyncPipelineRepository,
)


# ── Sync Tests ─────────────────────────────────────────────────────────────────

def test_repository_create_run(test_db_session):
    """Test creating a pipeline run."""
    repo = PipelineRepository(test_db_session)
    config = {"name": "test", "agents": []}

    run = repo.create_run(project_id="test-project", config=config, job_id="job-123")

    assert run.id is not None
    assert run.project_id == "test-project"
    assert run.config == config
    assert run.status == "pending"
    assert run.job_id == "job-123"
    assert run.created_at is not None


def test_repository_get_run(test_db_session):
    """Test retrieving a pipeline run."""
    repo = PipelineRepository(test_db_session)
    config = {"name": "test", "agents": []}

    created = repo.create_run(project_id="test-project", config=config)
    fetched = repo.get_run(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.project_id == "test-project"


def test_repository_update_run_status(test_db_session):
    """Test updating pipeline run status."""
    repo = PipelineRepository(test_db_session)
    config = {"name": "test", "agents": []}

    run = repo.create_run(project_id="test-project", config=config)
    updated = repo.update_run_status(run.id, status="running", started_at=datetime.utcnow())

    assert updated is not None
    assert updated.status == "running"
    assert updated.started_at is not None


def test_repository_list_runs(test_db_session):
    """Test listing pipeline runs for a project."""
    repo = PipelineRepository(test_db_session)
    config = {"name": "test", "agents": []}

    # Create 3 runs
    for i in range(3):
        repo.create_run(project_id="proj-1", config=config, job_id=f"job-{i}")
    for i in range(2):
        repo.create_run(project_id="proj-2", config=config, job_id=f"job2-{i}")

    # List for proj-1
    runs_proj1 = repo.list_runs(project_id="proj-1")
    assert len(runs_proj1) == 3

    # List for proj-2
    runs_proj2 = repo.list_runs(project_id="proj-2")
    assert len(runs_proj2) == 2


def test_repository_save_agent_result(test_db_session):
    """Test saving agent execution result."""
    repo = PipelineRepository(test_db_session)
    config = {"name": "test", "agents": []}

    run = repo.create_run(project_id="test-project", config=config)

    result = repo.save_agent_result(
        run_id=run.id,
        agent_name="backend",
        result={
            "output": "Backend API built successfully",
            "tokens": {"input": 1000, "output": 500},
            "cost_usd": 0.15,
            "duration_seconds": 25.5,
            "state": "done",
        }
    )

    assert result.id is not None
    assert result.agent_name == "backend"
    assert result.output == "Backend API built successfully"
    assert result.input_tokens == 1000
    assert result.output_tokens == 500
    assert result.cost_usd == 0.15


def test_repository_create_checkpoint(test_db_session):
    """Test creating a checkpoint."""
    repo = PipelineRepository(test_db_session)
    config = {"name": "test", "agents": []}

    run = repo.create_run(project_id="test-project", config=config)

    checkpoint = repo.create_checkpoint(
        pipeline_run_id=run.id,
        agent_name="checkpoint",
        checkpoint_type="human_approval",
        message="Approve this?",
        metadata={"approvers": ["user@co.com"]},
    )

    assert checkpoint.id is not None
    assert checkpoint.pipeline_run_id == run.id
    assert checkpoint.agent_name == "checkpoint"
    assert checkpoint.checkpoint_type == "human_approval"
    assert checkpoint.status == "pending"
    assert checkpoint.message == "Approve this?"
    assert checkpoint.metadata == {"approvers": ["user@co.com"]}


def test_repository_update_checkpoint_decision(test_db_session):
    """Test approving/rejecting a checkpoint."""
    repo = PipelineRepository(test_db_session)
    config = {"name": "test", "agents": []}

    run = repo.create_run(project_id="test-project", config=config)
    checkpoint = repo.create_checkpoint(
        pipeline_run_id=run.id,
        agent_name="checkpoint",
        checkpoint_type="human_approval",
        message="Test",
    )

    # Approve
    updated = repo.update_checkpoint_decision(checkpoint.id, status="approved", approver="admin@co.com")
    assert updated is not None
    assert updated.status == "approved"
    assert updated.approver == "admin@co.com"
    assert updated.decision_at is not None

    # Try to update again (should fail because not pending)
    again = repo.update_checkpoint_decision(checkpoint.id, status="rejected")
    assert again is None


# ── Async Tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_repository_create_run(async_test_db_session):
    """Test async repository create_run."""
    repo = AsyncPipelineRepository(async_test_db_session)
    config = {"name": "test", "agents": []}

    run = await repo.create_run(project_id="test-project", config=config, job_id="job-123")

    assert run.id is not None
    assert run.project_id == "test-project"
    assert run.status == "pending"


@pytest.mark.asyncio
async def test_async_repository_checkpoint_flow(async_test_db_session):
    """Test async checkpoint creation and decision."""
    repo = AsyncPipelineRepository(async_test_db_session)
    config = {"name": "test", "agents": []}

    run = await repo.create_run(project_id="test-project", config=config)

    # Create checkpoint
    checkpoint = await repo.create_checkpoint(
        pipeline_run_id=run.id,
        agent_name="checkpoint",
        checkpoint_type="budget_approval",
        message="Cost exceeds $1000",
    )
    assert checkpoint.status == "pending"

    # Get checkpoints for run
    checkpoints = await repo.get_checkpoints_for_run(run.id)
    assert len(checkpoints) == 1
    assert checkpoints[0].id == checkpoint.id

    # Approve
    updated = await repo.update_checkpoint_decision(checkpoint.id, status="approved", approver="finance@co.com")
    assert updated.status == "approved"
    assert updated.approver == "finance@co.com"


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """Create a synchronous test database session."""
    # Use in-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
async def async_test_db_session():
    """Create an async test database session."""
    # Use in-memory SQLite for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSession = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with AsyncSession() as session:
        yield session
        await session.rollback()

    await engine.dispose()
