Create AGENTS.md — DocuRebuild

You are working on DocuRebuild, a Local-First AI-Powered Document Reconstruction Workspace.

Before creating anything, understand the project context and its intended architecture. Create a comprehensive but practical "AGENTS.md" at the project root.

This file must serve as the permanent development instruction guide for all AI coding agents working on this project.

Core Product Principles

1. Local-First: User projects, databases, documents, and assets must remain locally controlled. Do not introduce Firebase, Supabase, or mandatory third-party cloud storage/database services.
2. Free Usage First: The application must remain useful without requiring paid AI subscriptions or paid API keys.
3. User-Controlled: Give users meaningful control over processing methods, AI providers, models, workflows, preferences, and application behavior.
4. Accuracy First: Preserve original information. Never silently invent, replace, or approve uncertain extracted content.
5. Manual + AI: Every important AI-assisted workflow should have a reasonable manual alternative.
6. Modular Architecture: Keep features, services, processing engines, and provider integrations independent and maintainable.
7. Production Quality: Prioritize reliability, security, accessibility, maintainability, and a polished user experience.

Free Usage First — Mandatory Rules

- Support local/offline processing wherever technically practical.
- Prefer genuinely free and locally executable solutions before paid services.
- Support optional free-tier API providers where available.
- Paid providers and paid API usage must always be optional.
- Never silently trigger paid API requests or paid operations.
- Clearly communicate free-tier limitations, quotas, availability, and possible costs.
- Require explicit user approval before using a paid service or exceeding a configured spending limit.
- Allow users to configure usage limits, preferred providers, fallback providers, and task-specific AI settings.
- Provide graceful fallbacks when an API is unavailable, rate-limited, or out of quota.
- Do not advertise a provider or model as free unless its current pricing and limitations are verified.
- Do not assume free API availability or quotas are permanent.
- The core application must remain usable without an internet connection or AI provider credentials, subject to local processing capabilities.

User Flexibility

- Prefer configurable settings over unnecessary fixed behavior.
- Make important processing and AI decisions user-selectable.
- Provide sensible defaults and optional presets for beginners.
- Keep advanced controls accessible without overwhelming the main interface.
- Avoid unnecessary restrictions on user workflows.
- Do not create configuration options that have no meaningful implementation or effect.

UI / UX Development Rules

- Build a consistent, reusable design system.
- Do not arbitrarily hardcode design values such as colors, font sizes, spacing, dimensions, margins, padding, border radius, or blur intensity.
- Determine appropriate values through the application's design system, responsive requirements, accessibility, and visual consistency.
- Respect system theme and application appearance settings.
- Keep the interface clean, minimal, polished, and responsive.
- Avoid unnecessary visual decoration, overcrowded controls, and excessive empty space.
- Use progressive disclosure for advanced settings.
- Maintain consistent interactions and feedback across the application.
- Support desktop, tablet, and mobile layouts appropriately.

Technical Rules

- Keep frontend, backend, database, processing engines, and AI provider integrations separated.
- Use clear interfaces and adapters for interchangeable engines and providers.
- Avoid unnecessary dependencies and duplicated implementations.
- Use dynamic provider/model discovery where supported instead of maintaining outdated hardcoded model lists.
- Never expose API keys or sensitive credentials in frontend code, logs, or plain-text storage.
- Preserve original imported files as immutable source assets.
- Use migrations for database schema changes.
- Handle errors, cancellation, retries, large files, and background processing properly.
- Keep application data and project data organized and portable.
- Write meaningful automated tests for important functionality.
- Update relevant documentation whenever architecture, features, settings, or workflows change.

AI Reliability Rules

- AI-generated content is a proposal until verified where accuracy matters.
- Preserve original values and track proposed changes.
- Record provider, model, task, timestamp, and verification status.
- Never fabricate missing table cells, equation symbols, figure labels, or numerical information.
- Clearly identify uncertain results and allow manual correction.
- Prefer structured and deterministic reconstruction over generative image replacement when exact information must be preserved.

Development Workflow

- Inspect the existing repository before making changes.
- Follow the architecture and specifications in "Prompt.md".
- Implement development phases sequentially.
- Do not skip incomplete functionality or replace real implementations with mock functionality.
- Run relevant tests and verify actual behavior before considering a task complete.
- Do not claim a feature works unless it has been implemented and tested.
- Keep code, documentation, and actual application behavior synchronized.
- Explain significant architectural decisions and technical limitations.

Important

These instructions apply throughout the project.

Do not interpret flexibility as permission to overcomplicate the application. Choose the simplest maintainable implementation that satisfies the product requirements.

Create the "AGENTS.md" file only. Do not begin implementing application features during this task.

Additional Development Rules: GitHub Integration, Backup & Internationalization

Add the following permanent development rules to AGENTS.md.

GitHub Integration and Repository Safety

- Support integration with an existing GitHub repository.
- The user will provide the repository URL before implementation begins.
- Treat the supplied repository as the authoritative remote repository unless the user explicitly requests otherwise.
- Never create a replacement repository unnecessarily.
- Never overwrite, delete, force-push, or rewrite existing remote history without explicit user authorization.
- Inspect the repository, branches, existing files, remotes, and project structure before making GitHub-related changes.
- Preserve existing source code, documentation, configuration, and user work.
- Keep credentials and access tokens out of source code, logs, commits, and documentation.
- Use secure GitHub authentication mechanisms available in the user's environment.
- Never assume that a repository URL alone grants write permissions.
- Request authentication or permission only when required.

Backup and Recovery

- Treat GitHub as an additional source-code and documentation backup, not as the primary storage location for user documents.
- Never upload private project documents, imported books, photographs, PDFs, extracted content, API keys, local databases, or personal assets to GitHub by default.
- Maintain a carefully designed ".gitignore".
- Separate application source code from local application data and user project data.
- Provide safe backup and recovery workflows.
- Verify backup results and remote synchronization status.
- Prefer reversible operations and maintain recovery options.
- Explain what will be uploaded before performing potentially sensitive operations.

GitHub-assisted Development

Use GitHub capabilities where appropriate for:

- Repository inspection.
- Commit and push.
- Pull and synchronization.
- Branch management.
- Release management.
- Issue tracking.
- Pull request workflows.
- Changelog and version history.
- Documentation updates.

Do not perform destructive or externally visible actions without appropriate user authorization.

Internationalization (i18n)

- English is the primary/default application language.
- Burmese is a supported secondary language.
- Build a proper localization architecture from the beginning.
- Avoid hardcoded user-facing strings throughout the frontend.
- Keep translations separate from application logic.
- Support language switching without requiring unnecessary application restarts.
- Ensure Burmese Unicode rendering and text input work correctly.
- Avoid destructive Zawgyi/Unicode conversions.
- Design layouts that can accommodate different text lengths and scripts.
- Use locale-aware date, number, and formatting behavior where appropriate.
- Make adding more languages possible without redesigning the localization architecture.

These requirements apply throughout the project.

UI Reference Interpretation & Design Direction

Use the attached DocuRebuild UI mockup strictly as a visual reference and design direction, not as a fixed template or a screen that must be copied exactly.

The purpose of this reference is to communicate the overall visual direction, workspace concept, layout preferences, and user experience I have in mind.

Important Instructions

1. Do not directly replicate the mockup.
   
   - Do not copy every component, button, panel, label, icon, or visual detail.
   - The mockup is conceptual and may contain placeholder content, unnecessary elements, or incomplete ideas.
   - Some elements may need to be redesigned, replaced, removed, or improved.

2. Think critically about the actual application.
   
   - Evaluate every UI element based on DocuRebuild's real functionality and architecture.
   - Add missing components and interactions that are genuinely useful.
   - Remove unnecessary, redundant, misleading, or decorative elements.
   - Reorganize layouts when doing so improves usability.
   - Do not introduce features simply because they appear in the reference.

3. Preserve the intended design direction.
   
   - Clean, polished, minimal, and professional.
   - Subtle Liquid Glass / Glassmorphism where appropriate.
   - Clear visual hierarchy and intuitive navigation.
   - Comfortable workspace for long document editing and reconstruction sessions.
   - Avoid overcrowded panels, excessive decoration, and unnecessary blank spaces.

4. Design around actual workflows.
   
   - Source image/PDF viewing and editing.
   - OCR and content extraction.
   - Table, figure, and equation reconstruction.
   - AI-assisted operations and verification.
   - Rich text document editing.
   - Project management, history, settings, and export.

5. Make the interface responsive and adaptive.
   
   - Desktop: prioritize the source viewer and document editor workspace.
   - Tablet: adapt panels and controls to available space.
   - Mobile: use an appropriate single-panel workflow with touch-friendly interactions.
   - Do not force the desktop layout onto smaller screens.

6. Follow the application's design system.
   
   - Do not arbitrarily hardcode colors, font sizes, spacing, dimensions, margins, padding, or blur values.
   - Use consistent design tokens, existing theme settings, and responsive layout rules.
   - Respect Light, Dark, and System themes, accent colors, font settings, and accessibility preferences.

Decision Priority

When the reference conflicts with actual functionality, usability, accessibility, responsiveness, or technical limitations, prioritize the actual application requirements.

You have the freedom to make better design decisions rather than blindly following the image.

Expected Result

Create a cohesive and production-quality DocuRebuild interface that captures the intention of the reference while improving its structure, usability, and completeness.

The final UI should feel purpose-built for DocuRebuild, not like a reproduction of a mockup.

The reference communicates what I want the application to feel like, not exactly what every screen must look like.