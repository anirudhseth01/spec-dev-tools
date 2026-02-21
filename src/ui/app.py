"""Main Streamlit app for Spec Builder Mode."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

import streamlit as st

from src.builder.session import (
    BuilderSession,
    SessionPhase,
    ResearchDepth,
    DISCUSSION_TOPICS,
    Decision,
)
from src.builder.persistence import SessionPersistence
from src.builder.discussion import DiscussionEngine, DiscussionAction
from src.builder.research import ResearchAgent
from src.builder.designer import BlockDesigner
from src.builder.generator import SpecGenerator
from src.llm.client import LLMClient, ClaudeCodeClient, ClaudeClient


# Available models
AVAILABLE_MODELS = {
    "Claude Opus 4.6": "claude-opus-4-6-20250514",
    "Claude Sonnet 4": "claude-sonnet-4-20250514",
    "Claude Haiku 3.5": "claude-3-5-haiku-20241022",
}
DEFAULT_MODEL = "Claude Opus 4.6"

# Phase to page mapping
PHASE_TO_PAGE = {
    SessionPhase.DISCUSSION: "💬 Discussion",
    SessionPhase.PAUSED: "💬 Discussion",
    SessionPhase.DESIGN: "🎨 Design",
    SessionPhase.REVIEW: "🎨 Design",
    SessionPhase.EXECUTION: "🚀 Execute",
    SessionPhase.COMPLETED: "🚀 Execute",
}

# Page config
st.set_page_config(
    page_title="Spec Builder",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "project_path" not in st.session_state:
    st.session_state.project_path = Path.cwd()

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

if "selected_model" not in st.session_state:
    st.session_state.selected_model = DEFAULT_MODEL

if "use_llm" not in st.session_state:
    st.session_state.use_llm = True

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "current_page" not in st.session_state:
    st.session_state.current_page = "🏠 Sessions"


def get_persistence() -> SessionPersistence:
    """Get persistence instance."""
    return SessionPersistence(st.session_state.project_path)


def get_llm_client() -> Optional[LLMClient]:
    """Get LLM client based on selected model."""
    if not st.session_state.use_llm:
        return None

    model_id = AVAILABLE_MODELS.get(st.session_state.selected_model)
    if not model_id:
        return None

    try:
        # Try Claude Code CLI first
        return ClaudeCodeClient(model=model_id, timeout=120)
    except Exception:
        try:
            # Fall back to API
            return ClaudeClient(model=model_id)
        except Exception:
            return None


def load_session(session_id: str) -> Optional[BuilderSession]:
    """Load a session by ID."""
    return get_persistence().load(session_id)


def save_session(session: BuilderSession) -> None:
    """Save a session."""
    get_persistence().save(session)


def get_page_for_phase(phase: SessionPhase) -> str:
    """Get the appropriate page for a session phase."""
    return PHASE_TO_PAGE.get(phase, "🏠 Sessions")


def navigate_to_page(page: str):
    """Navigate to a specific page."""
    st.session_state.current_page = page


def build_chat_context(session: Optional[BuilderSession], page: str) -> str:
    """Build context string for the chat based on current page and session."""
    context_parts = [f"Current page: {page}"]

    if session:
        context_parts.append(f"Session: {session.name}")
        context_parts.append(f"Phase: {session.phase.value}")
        context_parts.append(f"Description: {session.initial_description}")

        if session.decisions:
            context_parts.append("\nDecisions made:")
            for d in session.decisions:
                if d.is_decided:
                    opt = d.selected_option
                    context_parts.append(f"- {d.topic}: {opt.label if opt else d.user_notes}")

        if session.hierarchy_design:
            context_parts.append(f"\nHierarchy: {len(session.hierarchy_design.blocks)} blocks")
            for block in session.hierarchy_design.blocks[:5]:
                context_parts.append(f"- {block.name} ({block.block_type})")

        if session.reference_repos:
            context_parts.append(f"\nReference repos: {len(session.reference_repos)}")
            for repo in session.reference_repos:
                context_parts.append(f"- {repo.get('repo_name', 'Unknown')}")

    return "\n".join(context_parts)


def chat_with_claude(user_message: str, context: str) -> str:
    """Send a message to Claude and get a response."""
    llm_client = get_llm_client()
    if not llm_client:
        return "LLM is not enabled. Please enable it in the sidebar."

    system_prompt = f"""You are a helpful assistant for the Spec Builder tool, which helps users design and build software specifications.

Current context:
{context}

Help the user brainstorm, answer questions about their system design, suggest improvements, and guide them through the spec building process. Be concise but helpful."""

    try:
        response = llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_message,
            max_tokens=1024,
            temperature=0.7,
        )
        return response.content
    except Exception as e:
        return f"Error communicating with Claude: {str(e)}"


def render_chat_panel(session: Optional[BuilderSession], page: str):
    """Render the chat panel."""
    st.markdown("### 💬 Chat with Claude")
    st.caption("Brainstorm and discuss your system design")

    # Chat container
    chat_container = st.container(height=400)

    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask Claude anything..."):
        # Add user message
        st.session_state.chat_messages.append({"role": "user", "content": prompt})

        # Get response
        context = build_chat_context(session, page)
        with st.spinner("Thinking..."):
            response = chat_with_claude(prompt, context)

        # Add assistant message
        st.session_state.chat_messages.append({"role": "assistant", "content": response})
        st.rerun()

    # Clear chat button
    if st.session_state.chat_messages:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()


def main():
    """Main app entry point."""
    # Sidebar
    with st.sidebar:
        st.title("🏗️ Spec Builder")
        st.divider()

        # Model selector
        st.subheader("🤖 Model")
        selected_model = st.selectbox(
            "Select Model",
            options=list(AVAILABLE_MODELS.keys()),
            index=list(AVAILABLE_MODELS.keys()).index(st.session_state.selected_model),
            label_visibility="collapsed",
        )
        if selected_model != st.session_state.selected_model:
            st.session_state.selected_model = selected_model

        use_llm = st.toggle("Enable LLM", value=st.session_state.use_llm)
        if use_llm != st.session_state.use_llm:
            st.session_state.use_llm = use_llm

        if st.session_state.use_llm:
            st.caption(f"`{AVAILABLE_MODELS[st.session_state.selected_model]}`")
        else:
            st.caption("Using rule-based fallbacks")

        st.divider()

        # Project path (collapsed)
        with st.expander("📁 Project Settings"):
            project_path = st.text_input(
                "Project Path",
                value=str(st.session_state.project_path),
            )
            if project_path != str(st.session_state.project_path):
                st.session_state.project_path = Path(project_path)
                st.rerun()

        st.divider()

        # Navigation
        pages = ["🏠 Sessions", "➕ New Session", "💬 Discussion", "🎨 Design", "🚀 Execute", "📚 Reference Repos"]

        # Auto-navigate based on session phase
        if st.session_state.current_session_id:
            session = load_session(st.session_state.current_session_id)
            if session:
                suggested_page = get_page_for_phase(session.phase)
                if st.session_state.current_page not in ["🏠 Sessions", "➕ New Session", "📚 Reference Repos"]:
                    if st.session_state.current_page != suggested_page:
                        st.session_state.current_page = suggested_page

        current_index = pages.index(st.session_state.current_page) if st.session_state.current_page in pages else 0

        page = st.radio(
            "Navigation",
            pages,
            index=current_index,
            label_visibility="collapsed",
        )

        if page != st.session_state.current_page:
            st.session_state.current_page = page
            st.rerun()

        st.divider()

        # Current session info
        if st.session_state.current_session_id:
            session = load_session(st.session_state.current_session_id)
            if session:
                st.caption("Current Session")

                phase_colors = {
                    "discussion": "🟡",
                    "paused": "🔴",
                    "design": "🔵",
                    "review": "🟣",
                    "execution": "🔵",
                    "completed": "🟢",
                }
                phase_icon = phase_colors.get(session.phase.value, "⚪")

                st.info(f"**{session.name}**\n\n{phase_icon} {session.phase.value}")
                if st.button("✖️ Close Session", use_container_width=True):
                    st.session_state.current_session_id = None
                    st.session_state.current_page = "🏠 Sessions"
                    st.session_state.chat_messages = []
                    st.rerun()

    # Main content area with chat
    session = None
    if st.session_state.current_session_id:
        session = load_session(st.session_state.current_session_id)

    # Two-column layout: main content + chat
    if st.session_state.current_page not in ["🏠 Sessions", "➕ New Session"]:
        main_col, chat_col = st.columns([2, 1])
    else:
        main_col = st.container()
        chat_col = None

    with main_col:
        if st.session_state.current_page == "🏠 Sessions":
            render_sessions_page()
        elif st.session_state.current_page == "➕ New Session":
            render_new_session_page()
        elif st.session_state.current_page == "💬 Discussion":
            render_discussion_page()
        elif st.session_state.current_page == "🎨 Design":
            render_design_page()
        elif st.session_state.current_page == "🚀 Execute":
            render_execute_page()
        elif st.session_state.current_page == "📚 Reference Repos":
            render_repos_page()

    if chat_col:
        with chat_col:
            render_chat_panel(session, st.session_state.current_page)


def render_sessions_page():
    """Render sessions list page."""
    st.header("📋 Builder Sessions")

    persistence = get_persistence()
    sessions = persistence.list_sessions()

    if not sessions:
        st.info("No sessions found. Create a new session to get started!")
        if st.button("➕ Create New Session", type="primary"):
            navigate_to_page("➕ New Session")
            st.rerun()
        return

    # Session cards
    cols = st.columns(3)
    for i, session_info in enumerate(sessions):
        with cols[i % 3]:
            phase = session_info.get("phase", "unknown")
            phase_colors = {
                "discussion": "🟡",
                "design": "🔵",
                "review": "🟣",
                "execution": "🔵",
                "completed": "🟢",
                "paused": "🔴",
            }
            phase_icon = phase_colors.get(phase, "⚪")

            with st.container(border=True):
                st.subheader(f"{phase_icon} {session_info.get('name', 'Unnamed')}")
                st.caption(f"ID: `{session_info['id']}`")
                st.write(f"**Phase:** {phase}")

                updated = session_info.get("updated_at", "")
                if updated:
                    st.caption(f"Updated: {updated[:19]}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Open", key=f"open_{session_info['id']}", use_container_width=True):
                        st.session_state.current_session_id = session_info["id"]
                        st.session_state.chat_messages = []
                        # Navigate to appropriate page
                        session = load_session(session_info["id"])
                        if session:
                            navigate_to_page(get_page_for_phase(session.phase))
                        st.rerun()
                with col2:
                    if st.button("Delete", key=f"del_{session_info['id']}", use_container_width=True):
                        persistence.delete(session_info["id"])
                        if st.session_state.current_session_id == session_info["id"]:
                            st.session_state.current_session_id = None
                        st.rerun()


def render_new_session_page():
    """Render new session creation page."""
    st.header("➕ Create New Session")

    with st.form("new_session_form"):
        name = st.text_input(
            "Session Name",
            placeholder="e.g., payment-system, auth-service",
        )

        description = st.text_area(
            "Initial Description",
            placeholder="Describe what you want to build...",
            height=100,
        )

        col1, col2 = st.columns(2)
        with col1:
            research_depth = st.selectbox(
                "Research Depth",
                ["light", "medium", "deep"],
                index=1,
            )
        with col2:
            specs_dir = st.text_input(
                "Specs Directory",
                value="specs",
            )

        submitted = st.form_submit_button("Create Session", type="primary", use_container_width=True)

        if submitted:
            if not name:
                st.error("Please provide a session name")
            else:
                session = BuilderSession(
                    name=name,
                    initial_description=description,
                    research_depth=ResearchDepth(research_depth),
                    project_root=str(st.session_state.project_path),
                    specs_dir=specs_dir,
                )
                save_session(session)
                st.session_state.current_session_id = session.id
                st.session_state.chat_messages = []
                st.success(f"Created session: {session.id}")
                st.balloons()
                # Auto-navigate to discussion
                navigate_to_page("💬 Discussion")
                st.rerun()


def render_discussion_page():
    """Render discussion/Q&A page."""
    st.header("💬 Discussion Phase")

    if not st.session_state.current_session_id:
        st.warning("Please select or create a session first.")
        if st.button("Go to Sessions"):
            navigate_to_page("🏠 Sessions")
            st.rerun()
        return

    session = load_session(st.session_state.current_session_id)
    if not session:
        st.error("Session not found")
        return

    if session.phase not in [SessionPhase.DISCUSSION, SessionPhase.PAUSED]:
        st.info(f"Session is in **{session.phase.value}** phase.")
        if st.button("Go to Design →", type="primary"):
            navigate_to_page("🎨 Design")
            st.rerun()
        return

    # Progress indicator
    total_topics = len(DISCUSSION_TOPICS)
    current_idx = session.current_topic_index
    progress = min(current_idx / total_topics, 1.0)

    st.progress(progress, text=f"Topic {min(current_idx + 1, total_topics)} of {total_topics}")

    # Show current topic
    if current_idx < total_topics:
        current_topic = DISCUSSION_TOPICS[current_idx]

        st.subheader(f"📌 {current_topic['name']}")

        if current_topic.get("research_enabled"):
            st.caption("🔬 Research-enabled topic")

        # Get or create discussion engine
        llm_client = get_llm_client()
        research_agent = ResearchAgent(llm_client, session.research_depth)
        engine = DiscussionEngine(session, llm_client, research_agent)

        # Check if we need to generate a question
        current_decision = None
        for d in reversed(session.decisions):
            if d.topic == current_topic["name"] and not d.is_decided:
                current_decision = d
                break

        if not current_decision:
            # Generate new question
            with st.spinner("Generating question..."):
                question, options = asyncio.run(engine.generate_question(current_topic["name"]))

            current_decision = Decision(
                id=f"dec-{uuid.uuid4().hex[:8]}",
                topic=current_topic["name"],
                question=question,
                options=options,
            )
            session.add_decision(current_decision)
            save_session(session)

        # Display question
        st.markdown(f"**{current_decision.question}**")

        # Display options
        selected_option = None
        for i, opt in enumerate(current_decision.options):
            with st.container(border=True):
                col1, col2 = st.columns([0.08, 0.92])
                with col1:
                    if st.button(f"{i+1}", key=f"opt_{opt.id}", use_container_width=True):
                        selected_option = opt
                with col2:
                    st.markdown(f"**{opt.label}**")
                    st.write(opt.description)
                    if opt.pros or opt.cons:
                        pcol1, pcol2 = st.columns(2)
                        with pcol1:
                            for pro in opt.pros:
                                st.markdown(f"✅ {pro}")
                        with pcol2:
                            for con in opt.cons:
                                st.markdown(f"⚠️ {con}")

        # Custom answer
        with st.expander("💡 Custom answer"):
            custom_answer = st.text_area("Your approach", key="custom_answer", label_visibility="collapsed")
            if st.button("Submit Custom"):
                if custom_answer:
                    current_decision.user_notes = custom_answer
                    current_decision.timestamp = datetime.now()
                    session.advance_topic()
                    save_session(session)
                    st.rerun()

        # Handle selection
        if selected_option:
            current_decision.selected_option_id = selected_option.id
            current_decision.timestamp = datetime.now()
            session.advance_topic()
            save_session(session)
            st.rerun()

    else:
        # Discussion complete
        st.success("🎉 All topics covered!")

        if st.button("Proceed to Design →", type="primary"):
            session.transition_to(SessionPhase.DESIGN)
            save_session(session)
            navigate_to_page("🎨 Design")
            st.rerun()

    # Show decisions made
    st.divider()
    with st.expander("📝 Decisions Made", expanded=False):
        for d in session.decisions:
            if d.is_decided:
                opt = d.selected_option
                st.markdown(f"**{d.topic}:** {opt.label if opt else d.user_notes}")


def render_design_page():
    """Render design/review page."""
    st.header("🎨 Design Phase")

    if not st.session_state.current_session_id:
        st.warning("Please select or create a session first.")
        return

    session = load_session(st.session_state.current_session_id)
    if not session:
        st.error("Session not found")
        return

    if session.phase == SessionPhase.DISCUSSION:
        st.info("Complete the discussion phase first.")
        if st.button("← Go to Discussion"):
            navigate_to_page("💬 Discussion")
            st.rerun()
        return

    # Generate hierarchy if needed
    if not session.hierarchy_design:
        st.subheader("🔧 Generate Block Hierarchy")

        # Show decisions summary
        st.write("Based on your decisions:")
        for d in session.decisions:
            if d.is_decided:
                opt = d.selected_option
                st.markdown(f"- **{d.topic}:** {opt.label if opt else d.user_notes}")

        if st.button("Generate Hierarchy", type="primary"):
            with st.spinner("Designing block hierarchy..."):
                llm_client = get_llm_client()
                designer = BlockDesigner(llm_client)
                hierarchy = asyncio.run(designer.design_hierarchy(session))
                session.hierarchy_design = hierarchy
                session.transition_to(SessionPhase.REVIEW)
                save_session(session)
                st.rerun()
        return

    # Display hierarchy
    hierarchy = session.hierarchy_design

    st.subheader(f"📦 {hierarchy.root_name}")
    st.caption(f"{len(hierarchy.blocks)} blocks")

    for block in hierarchy.blocks:
        depth = block.path.count("/")
        indent = "　" * depth

        type_icons = {"root": "🏠", "component": "📦", "module": "📁", "leaf": "📄"}
        icon = type_icons.get(block.block_type, "📄")

        with st.container(border=True):
            st.markdown(f"{indent}{icon} **{block.name}** `{block.block_type}`")
            st.caption(f"{indent}{block.description}")
            if block.tech_stack:
                st.markdown(f"{indent}🔧 {block.tech_stack}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Approve & Generate Specs", type="primary", use_container_width=True):
            with st.spinner("Generating spec files..."):
                llm_client = get_llm_client()
                generator = SpecGenerator(llm_client)
                specs = asyncio.run(generator.generate_all_specs(hierarchy, session))
                created_files = asyncio.run(generator.write_specs(specs, st.session_state.project_path))

                session.transition_to(SessionPhase.EXECUTION)
                save_session(session)

                st.success(f"Generated {len(specs)} spec files!")
                navigate_to_page("🚀 Execute")
                st.rerun()

    with col2:
        if st.button("🔄 Regenerate", use_container_width=True):
            session.hierarchy_design = None
            session.transition_to(SessionPhase.DESIGN)
            save_session(session)
            st.rerun()


def render_execute_page():
    """Render execution page."""
    st.header("🚀 Execution Phase")

    if not st.session_state.current_session_id:
        st.warning("Please select or create a session first.")
        return

    session = load_session(st.session_state.current_session_id)
    if not session:
        st.error("Session not found")
        return

    if session.phase not in [SessionPhase.EXECUTION, SessionPhase.COMPLETED]:
        st.info(f"Session is in **{session.phase.value}** phase.")
        return

    if not session.hierarchy_design:
        st.error("No hierarchy design found.")
        return

    if session.phase == SessionPhase.COMPLETED:
        st.success("🎉 Execution completed!")

    hierarchy = session.hierarchy_design

    st.subheader("📊 Execution Plan")
    st.write(f"**{len(hierarchy.blocks)} blocks** to implement:")

    for block in hierarchy.blocks:
        status = session.execution_progress.block_statuses.get(block.path, "pending")
        icons = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}
        icon = icons.get(status, "⏳")

        with st.container(border=True):
            col1, col2 = st.columns([0.9, 0.1])
            with col1:
                st.markdown(f"{icon} **{block.name}** (`{block.path}`)")
            with col2:
                st.caption(status)

    st.divider()
    st.info("Run execution from CLI: `spec-dev build execute " + st.session_state.current_session_id + "`")


def render_repos_page():
    """Render reference repositories page."""
    st.header("📚 Reference Repositories")

    if not st.session_state.current_session_id:
        st.warning("Please select or create a session first.")
        return

    session = load_session(st.session_state.current_session_id)
    if not session:
        st.error("Session not found")
        return

    # Add new repo
    with st.form("add_repo_form"):
        repo_url = st.text_input("GitHub Repository URL", placeholder="https://github.com/owner/repo")
        submitted = st.form_submit_button("Analyze Repository", use_container_width=True)

        if submitted and repo_url:
            with st.spinner("Analyzing repository..."):
                llm_client = get_llm_client()
                research_agent = ResearchAgent(llm_client, session.research_depth)
                engine = DiscussionEngine(session, llm_client, research_agent)
                result = asyncio.run(engine.add_reference_repo(repo_url))
                save_session(session)

                if result.action == DiscussionAction.ANALYZE_REPO:
                    st.success("Repository analyzed!")
                else:
                    st.error(result.message)
                st.rerun()

    st.divider()

    if not session.reference_repos:
        st.info("No reference repositories added yet.")
        return

    for repo in session.reference_repos:
        with st.container(border=True):
            col1, col2 = st.columns([0.8, 0.2])
            with col1:
                st.markdown(f"### {repo.get('repo_name', 'Unknown')}")
                st.caption(repo.get('repo_url', ''))
            with col2:
                st.metric("Language", repo.get('primary_language', '-'))

            if repo.get('description'):
                st.write(repo['description'])

            key_files = repo.get('key_files', [])
            if key_files:
                with st.expander(f"📁 Key Files ({len(key_files)})"):
                    for f in key_files:
                        st.code(f.get('path', ''))

            components = repo.get('reusable_components', [])
            if components:
                with st.expander(f"🧩 Components ({len(components)})"):
                    for comp in components:
                        st.markdown(f"**{comp.get('name')}** ({comp.get('component_type', '-')})")
                        st.write(comp.get('description', ''))


if __name__ == "__main__":
    main()
