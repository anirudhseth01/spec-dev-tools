"""Main Streamlit app for Spec Builder Mode."""

from __future__ import annotations

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

import streamlit as st

from src.builder.session import (
    BuilderSession,
    SessionPhase,
    ResearchDepth,
    DISCUSSION_TOPICS,
)
from src.builder.persistence import SessionPersistence
from src.builder.discussion import DiscussionEngine, DiscussionAction
from src.builder.research import ResearchAgent
from src.builder.designer import BlockDesigner
from src.builder.generator import SpecGenerator


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


def get_persistence() -> SessionPersistence:
    """Get persistence instance."""
    return SessionPersistence(st.session_state.project_path)


def load_session(session_id: str) -> Optional[BuilderSession]:
    """Load a session by ID."""
    return get_persistence().load(session_id)


def save_session(session: BuilderSession) -> None:
    """Save a session."""
    get_persistence().save(session)


def main():
    """Main app entry point."""
    # Sidebar navigation
    with st.sidebar:
        st.title("🏗️ Spec Builder")
        st.divider()

        # Project path
        project_path = st.text_input(
            "Project Path",
            value=str(st.session_state.project_path),
            help="Path to your project directory",
        )
        if project_path != str(st.session_state.project_path):
            st.session_state.project_path = Path(project_path)
            st.rerun()

        st.divider()

        # Navigation
        page = st.radio(
            "Navigation",
            ["🏠 Sessions", "➕ New Session", "💬 Discussion", "🎨 Design", "🚀 Execute", "📚 Reference Repos"],
            label_visibility="collapsed",
        )

        st.divider()

        # Current session info
        if st.session_state.current_session_id:
            session = load_session(st.session_state.current_session_id)
            if session:
                st.caption("Current Session")
                st.info(f"**{session.name}**\n\nPhase: {session.phase.value}")
                if st.button("Clear Selection", use_container_width=True):
                    st.session_state.current_session_id = None
                    st.rerun()

    # Route to pages
    if page == "🏠 Sessions":
        render_sessions_page()
    elif page == "➕ New Session":
        render_new_session_page()
    elif page == "💬 Discussion":
        render_discussion_page()
    elif page == "🎨 Design":
        render_design_page()
    elif page == "🚀 Execute":
        render_execute_page()
    elif page == "📚 Reference Repos":
        render_repos_page()


def render_sessions_page():
    """Render sessions list page."""
    st.header("📋 Builder Sessions")

    persistence = get_persistence()
    sessions = persistence.list_sessions()

    if not sessions:
        st.info("No sessions found. Create a new session to get started!")
        if st.button("➕ Create New Session", type="primary"):
            st.session_state.page = "➕ New Session"
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
                        st.rerun()
                with col2:
                    if st.button("Delete", key=f"del_{session_info['id']}", use_container_width=True):
                        persistence.delete(session_info["id"])
                        st.rerun()


def render_new_session_page():
    """Render new session creation page."""
    st.header("➕ Create New Session")

    with st.form("new_session_form"):
        name = st.text_input(
            "Session Name",
            placeholder="e.g., payment-system, auth-service",
            help="A short name for your system",
        )

        description = st.text_area(
            "Initial Description",
            placeholder="Describe what you want to build...",
            help="A brief description of the system you want to build",
            height=100,
        )

        col1, col2 = st.columns(2)
        with col1:
            research_depth = st.selectbox(
                "Research Depth",
                ["light", "medium", "deep"],
                index=1,
                help="How deep to research technology choices",
            )
        with col2:
            specs_dir = st.text_input(
                "Specs Directory",
                value="specs",
                help="Directory to store generated specs",
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
                st.success(f"Created session: {session.id}")
                st.balloons()
                st.rerun()


def render_discussion_page():
    """Render discussion/Q&A page."""
    st.header("💬 Discussion Phase")

    if not st.session_state.current_session_id:
        st.warning("Please select or create a session first.")
        return

    session = load_session(st.session_state.current_session_id)
    if not session:
        st.error("Session not found")
        return

    if session.phase not in [SessionPhase.DISCUSSION, SessionPhase.PAUSED]:
        st.info(f"Session is in **{session.phase.value}** phase, not discussion.")
        if session.phase == SessionPhase.DESIGN:
            st.write("Go to the Design page to continue.")
        elif session.phase == SessionPhase.REVIEW:
            st.write("Go to the Design page to review and approve.")
        return

    # Progress indicator
    total_topics = len(DISCUSSION_TOPICS)
    current_idx = session.current_topic_index
    progress = min(current_idx / total_topics, 1.0)

    st.progress(progress, text=f"Topic {min(current_idx + 1, total_topics)} of {total_topics}")

    # Topic tabs
    topic_names = [t["name"] for t in DISCUSSION_TOPICS]

    # Show current topic
    if current_idx < total_topics:
        current_topic = DISCUSSION_TOPICS[current_idx]

        st.subheader(f"📌 {current_topic['name']}")

        if current_topic.get("research_enabled"):
            st.caption("🔬 Research-enabled topic")

        # Get or create discussion engine
        research_agent = ResearchAgent(None, session.research_depth)
        engine = DiscussionEngine(session, None, research_agent)

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

            # Create decision
            import uuid
            from src.builder.session import Decision
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

        # Display options as cards
        st.write("")

        selected_option = None
        for i, opt in enumerate(current_decision.options):
            with st.container(border=True):
                col1, col2 = st.columns([0.1, 0.9])
                with col1:
                    if st.button(f"{i+1}", key=f"opt_{opt.id}", use_container_width=True):
                        selected_option = opt
                with col2:
                    st.markdown(f"**{opt.label}**")
                    st.write(opt.description)

                    if opt.pros or opt.cons:
                        pcol1, pcol2 = st.columns(2)
                        with pcol1:
                            if opt.pros:
                                for pro in opt.pros:
                                    st.markdown(f"✅ {pro}")
                        with pcol2:
                            if opt.cons:
                                for con in opt.cons:
                                    st.markdown(f"⚠️ {con}")

        # Custom answer
        st.write("")
        with st.expander("💡 Or provide a custom answer"):
            custom_answer = st.text_area(
                "Your custom approach",
                key="custom_answer",
                placeholder="Describe your preferred approach...",
            )
            if st.button("Submit Custom Answer"):
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
        st.write("You can now proceed to the design phase.")

        if st.button("Proceed to Design", type="primary"):
            session.transition_to(SessionPhase.DESIGN)
            save_session(session)
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
        return

    # Generate hierarchy if needed
    if not session.hierarchy_design:
        st.subheader("🔧 Generating Block Hierarchy")

        if st.button("Generate Hierarchy", type="primary"):
            with st.spinner("Designing block hierarchy from decisions..."):
                designer = BlockDesigner(None)
                hierarchy = asyncio.run(designer.design_hierarchy(session))
                session.hierarchy_design = hierarchy
                session.transition_to(SessionPhase.REVIEW)
                save_session(session)
                st.rerun()

        # Show decisions summary
        st.subheader("📝 Decisions Summary")
        for d in session.decisions:
            if d.is_decided:
                opt = d.selected_option
                st.markdown(f"- **{d.topic}:** {opt.label if opt else d.user_notes}")
        return

    # Display hierarchy
    hierarchy = session.hierarchy_design

    st.subheader(f"📦 {hierarchy.root_name}")
    st.caption(f"{len(hierarchy.blocks)} blocks")

    # Tree view
    for block in hierarchy.blocks:
        depth = block.path.count("/")
        indent = "&nbsp;" * (depth * 4)

        type_icons = {
            "root": "🏠",
            "component": "📦",
            "module": "📁",
            "leaf": "📄",
        }
        icon = type_icons.get(block.block_type, "📄")

        with st.container(border=True):
            st.markdown(f"{indent}{icon} **{block.name}** `{block.block_type}`")
            st.caption(f"{indent}{block.description}")

            if block.tech_stack:
                st.markdown(f"{indent}🔧 {block.tech_stack}")
            if block.dependencies:
                st.markdown(f"{indent}🔗 Depends on: {', '.join(block.dependencies)}")

    # Approval section
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Approve & Generate Specs", type="primary", use_container_width=True):
            with st.spinner("Generating spec files..."):
                generator = SpecGenerator(None)
                specs = asyncio.run(generator.generate_all_specs(hierarchy, session))
                created_files = asyncio.run(
                    generator.write_specs(specs, st.session_state.project_path)
                )

                session.transition_to(SessionPhase.EXECUTION)
                save_session(session)

                st.success(f"Generated {len(specs)} spec files!")
                with st.expander("Created Files"):
                    for f in created_files:
                        st.code(f)
                st.rerun()

    with col2:
        if st.button("🔄 Regenerate Hierarchy", use_container_width=True):
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

    if session.phase != SessionPhase.EXECUTION:
        st.info(f"Session is in **{session.phase.value}** phase.")
        if session.phase == SessionPhase.COMPLETED:
            st.success("Execution completed!")
        return

    if not session.hierarchy_design:
        st.error("No hierarchy design found.")
        return

    hierarchy = session.hierarchy_design

    st.subheader("📊 Execution Plan")

    # Show blocks to execute
    st.write(f"**{len(hierarchy.blocks)} blocks** to implement:")

    for block in hierarchy.blocks:
        status = session.execution_progress.block_statuses.get(block.path, "pending")
        status_icons = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }
        icon = status_icons.get(status, "⏳")

        with st.container(border=True):
            col1, col2 = st.columns([0.9, 0.1])
            with col1:
                st.markdown(f"{icon} **{block.name}** (`{block.path}`)")
            with col2:
                st.caption(status)

    st.divider()

    # Execution controls
    st.info("⚠️ Execution feature runs the agent pipeline for each block. "
            "This requires a configured LLM and may take some time.")

    col1, col2 = st.columns(2)
    with col1:
        dry_run = st.checkbox("Dry Run", value=True, help="Preview without writing files")
    with col2:
        skip_tests = st.checkbox("Skip Tests", help="Skip test generation")

    if st.button("▶️ Start Execution", type="primary", use_container_width=True, disabled=True):
        st.warning("Execution from UI is not yet implemented. Use CLI: `spec-dev build execute`")


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
    st.subheader("➕ Add Repository")

    with st.form("add_repo_form"):
        repo_url = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/owner/repo",
            help="Enter a public GitHub repository URL to analyze",
        )

        submitted = st.form_submit_button("Analyze Repository", use_container_width=True)

        if submitted and repo_url:
            with st.spinner("Analyzing repository..."):
                research_agent = ResearchAgent(None, session.research_depth)
                engine = DiscussionEngine(session, None, research_agent)

                result = asyncio.run(engine.add_reference_repo(repo_url))
                save_session(session)

                if result.action == DiscussionAction.ANALYZE_REPO:
                    st.success("Repository analyzed!")
                else:
                    st.error(result.message)
                st.rerun()

    # Display existing repos
    st.divider()
    st.subheader("📋 Analyzed Repositories")

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

            # Key files
            key_files = repo.get('key_files', [])
            if key_files:
                with st.expander(f"📁 Key Files ({len(key_files)})"):
                    for f in key_files:
                        st.code(f.get('path', ''), language=f.get('language', ''))

            # Reusable components
            components = repo.get('reusable_components', [])
            if components:
                with st.expander(f"🧩 Reusable Components ({len(components)})"):
                    for comp in components:
                        st.markdown(f"**{comp.get('name', 'Unknown')}** ({comp.get('component_type', '-')})")
                        st.write(comp.get('description', ''))
                        if comp.get('code_snippet'):
                            st.code(comp['code_snippet'], language='python')

            # Patterns
            patterns = repo.get('architecture_patterns', [])
            if patterns:
                st.write("**Patterns:** " + ", ".join(patterns))


if __name__ == "__main__":
    main()
