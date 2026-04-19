import uuid
from datetime import datetime
from sqlalchemy import (Column, String, Integer, Float, Boolean, Text, DateTime,
                        BigInteger, ForeignKey, LargeBinary, Index)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, INET
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_id = Column(BigInteger, nullable=False, unique=True)
    github_username = Column(String(255), nullable=False)
    email = Column(String(255))
    github_avatar_url = Column(Text)
    github_token_encrypted = Column(LargeBinary, nullable=False)
    github_token_iv = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    repo_full_name = Column(String(255), nullable=False)
    repo_name = Column(String(255), nullable=False)
    repo_owner = Column(String(255), nullable=False)
    default_branch = Column(String(255), nullable=False, default="main")
    webhook_id = Column(BigInteger)
    webhook_secret = Column(String(255))
    status = Column(String(50), nullable=False, default="pending")
    last_indexed_at = Column(DateTime(timezone=True))
    last_commit_sha = Column(String(40))
    file_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    doc_coverage_score = Column(Float)
    config = Column(JSONB, nullable=False, default={"auto_update": True, "auto_pr": True, "quality_threshold": 0.7})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="projects")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="project", cascade="all, delete-orphan")
    __table_args__ = (Index("idx_projects_user_id", "user_id"), Index("idx_projects_repo", "repo_full_name"))

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(Text, nullable=False)
    doc_type = Column(String(50), nullable=False)
    generated_type = Column(String(50))
    title = Column(String(500))
    content_raw = Column(Text)
    content_processed = Column(Text)
    content_hash = Column(String(64))
    status = Column(String(50), nullable=False, default="current")
    quality_score = Column(Float)
    quality_details = Column(JSONB)
    language = Column(String(50))
    last_code_commit = Column(String(40))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    project = relationship("Project", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    __table_args__ = (Index("idx_documents_project_id", "project_id"), Index("idx_documents_status", "status"))

class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_type = Column(String(50), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    start_line = Column(Integer)
    end_line = Column(Integer)
    token_count = Column(Integer, nullable=False)
    symbol_name = Column(String(255))
    is_public = Column(Boolean, default=True)
    parent_context = Column(Text)
    embedding_id = Column(String(255))
    metadata = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    document = relationship("Document", back_populates="chunks")
    project = relationship("Project", back_populates="chunks")
    __table_args__ = (Index("idx_chunks_document_id", "document_id"),
                      Index("idx_chunks_project_id", "project_id"),
                      Index("idx_chunks_symbol", "project_id", "symbol_name"))

class AgentTask(Base):
    __tablename__ = "agent_tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="queued")
    input = Column(JSONB, nullable=False, default={})
    output = Column(JSONB)
    progress = Column(JSONB)
    triggered_by = Column(String(50), nullable=False, default="manual")
    error_message = Column(Text)
    tokens_used = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    __table_args__ = (Index("idx_agent_tasks_project_id", "project_id"),
                      Index("idx_agent_tasks_status", "status"))

class Query(Base):
    __tablename__ = "queries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    channel = Column(String(50), nullable=False)
    query_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=False)
    chunks_used = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=[])
    confidence_score = Column(Float, nullable=False)
    feedback = Column(String(20))
    latency_ms = Column(Integer, nullable=False)
    conversation_id = Column(UUID(as_uuid=True))
    metadata = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    __table_args__ = (Index("idx_queries_project_id", "project_id"),
                      Index("idx_queries_channel", "channel"),
                      Index("idx_queries_created_at", "created_at"))

class Integration(Base):
    __tablename__ = "integrations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="active")
    config = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("idx_integrations_project_id", "project_id"),)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(UUID(as_uuid=True))
    metadata = Column(JSONB, nullable=False, default={})
    ip_address = Column(INET)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    __table_args__ = (Index("idx_audit_logs_action", "action"),
                      Index("idx_audit_logs_created_at", "created_at"))
