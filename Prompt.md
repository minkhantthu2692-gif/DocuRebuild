Create Prompt.md — Complete DocuRebuild Project Specification

You are an experienced software architect, product designer, and full-stack engineer.

Your task is to create a comprehensive "Prompt.md" file for DocuRebuild, a Local-First AI-Powered Document Reconstruction Workspace.

This document will serve as the primary product specification, technical architecture reference, and phased development roadmap for the entire project.

Read the root "AGENTS.md" first and follow its instructions.

Do not start implementing the application yet. First, create a complete and technically realistic project specification.

1. Product Vision

DocuRebuild helps users transform scanned books, textbook pages, photographs, screenshots, and PDF documents into accurate, structured, editable documents.

The application must support both manual workflows and AI-assisted workflows.

Its purpose is not simply OCR or image-to-text conversion. It is a complete document reconstruction workspace that preserves original information while making extracted content editable and reusable.

2. Fundamental Product Principles

Use these principles throughout the entire specification:

- Local-First.
- Free Usage First.
- User-Controlled and Flexible.
- Accuracy First.
- Manual + AI Workflows.
- Privacy and Data Ownership.
- Modular and Extensible Architecture.
- Production-Quality User Experience.

The application must remain useful without paid API access.

3. Free Usage First AI Strategy

This is a major product requirement.

Design the AI system so that users are not forced to purchase API access.

Support three categories:

A. Local AI

- Ollama.
- LM Studio.
- Other compatible local inference servers where practical.
- Offline-capable models.
- User-configurable model endpoints and settings.

B. Free-Tier API Providers

- Support providers offering free API access or free usage quotas when available.
- Treat free quotas and availability as dynamic.
- Allow users to configure providers and models.
- Display applicable limitations, quota information, and availability when supported.

C. Paid API Providers

- Optional only.
- Never required for the application's core functionality.
- Never use paid services without explicit user approval.
- Allow user-defined spending limits and usage restrictions.

Implement a provider adapter architecture supporting:

1. OpenAI
2. Google Gemini
3. Anthropic
4. OpenRouter
5. Groq
6. DeepSeek
7. Mistral
8. xAI
9. Together AI
10. Custom OpenAI-Compatible Endpoints

Do not assume every provider offers a free tier, identical API compatibility, model discovery, or the same capabilities.

Verify provider capabilities through official documentation and actual integration tests.

Avoid hardcoded model lists. Implement dynamic model discovery when supported, with manual model entry as a fallback.

Independent AI Profiles

Provide three independently configurable profiles:

- Vision AI.
- Text & Reasoning AI.
- Image Generation AI.

Each profile should support provider selection, model selection, connection configuration, testing, and optional fallback configuration.

Users must be able to override the selected profile/model for individual tasks.

AI Usage Management

Include:

- Free/Paid/Local provider classification.
- Usage tracking where provider information permits.
- Configurable request and usage limits.
- Cost estimation where reliable pricing information is available.
- Provider availability and connection testing.
- Rate-limit handling.
- Fallback routing.
- Task-specific provider selection.
- Usage history.
- Explicit confirmation before paid operations.
- API key management using secure storage.

Never promise unlimited free AI access.

Manual and local alternatives must remain available when providers are unavailable.

4. User Flexibility and Configuration System

The application should give users control over nearly all meaningful application behaviors.

Design a structured settings system covering:

- OCR engine and OCR workflow.
- OCR language selection.
- Image processing methods.
- PDF extraction methods.
- AI provider and model selection.
- AI task routing.
- AI usage limits.
- Local AI connections.
- Export preferences.
- Document page layout.
- Editor behavior.
- Application appearance.
- Storage and backup preferences.
- History and retention.
- Performance and processing options.

Use sensible defaults and optional presets.

Organize settings into Basic and Advanced sections where appropriate.

Do not expose meaningless or redundant options.

Every setting must have a clear purpose, predictable behavior, validation, and persistence.

5. Platform and Runtime Architecture

Selected architecture decisions:

- Runtime: Hybrid.
- Platform: Desktop, Tablet, and Mobile.
- Distribution: Web/PWA and Desktop.
- OCR: Hybrid, with selectable workflows.
- PDF: Both text-based and image-based PDFs.
- Languages: English, Burmese, and other languages.
- Storage: Project-based local storage.
- AI: BYOK + Local AI.
- Development: Phased.
- Priority: Accuracy.

Design the architecture around these decisions.

The desktop application should use a local backend and local processing engines.

The web/PWA version must clearly distinguish between browser capabilities and local backend capabilities.

Do not pretend that a browser-only PWA can run every native Python OCR or PDF-processing dependency.

Mobile should provide an adaptive workflow, camera import, and an optional secure connection to a user's own processing host where practical.

If remote access to a local backend is supported, design explicit pairing, authentication, access control, and secure communication. Do not expose the backend publicly by default.

6. Recommended Technology Stack

Evaluate and use the following stack unless a technically justified alternative is better:

Frontend

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- shadcn/ui.
- Framer Motion.

Rich Text Editor

- Tiptap.

Mathematics

- KaTeX.
- MathLive.
- LaTeX.
- OMML for native Microsoft Word equations.

Backend

- Python.
- FastAPI.

Database

- SQLite.
- SQLAlchemy.
- Alembic.

Processing

- OpenCV.
- Pillow.
- PyMuPDF.

OCR

- PaddleOCR.
- Tesseract.
- Other suitable engines through adapters.

Benchmark English and Burmese OCR independently. Do not assume one OCR engine provides equally good support for both.

Background Processing

- SQLite-backed job management or another appropriately lightweight local solution.
- Avoid mandatory Redis unless a demonstrated requirement justifies it.

Desktop

- Tauri.
- Python backend sidecar where appropriate.

Document Export

- python-docx.
- OMML generation and validation for Word equations.

Testing

- Pytest.
- Vitest.
- Playwright.

Explain important trade-offs and packaging limitations.

7. Core Application Modules

Design the application around independent modules:

1. Project Manager.
2. Import Manager.
3. Image Processing Engine.
4. PDF Engine.
5. OCR Engine.
6. Layout Detection Engine.
7. Element Extraction Engine.
8. AI Gateway.
9. AI Task Router.
10. Document Editor.
11. Document Model.
12. Export Engine.
13. History Manager.
14. Storage Manager.

Define each module's responsibilities, interfaces, dependencies, and interactions.

8. Import and PDF Processing

Support:

- JPG/JPEG.
- PNG.
- WEBP.
- BMP.
- TIFF.
- Text-based PDF.
- Image-based PDF.
- Mixed PDF.

Include:

- Multiple-file import.
- Drag and drop.
- Clipboard paste.
- Camera import where supported.
- PDF page rendering.
- Embedded PDF text extraction.
- Page navigation and reordering.
- Page-level processing.
- Large document handling.

Prefer direct embedded-text extraction when possible instead of unnecessarily rendering and OCR-processing every PDF page.

9. Image Processing

Provide manual and automatic controls for:

- Rotation.
- Cropping.
- Deskewing.
- Perspective correction.
- Contrast.
- Sharpening.
- Denoising.
- Thresholding.
- Shadow removal.
- Background cleanup.
- Dewarping.

Keep original imported images immutable.

Save processed versions separately and allow users to compare or restore them.

10. OCR and Layout Detection

Support selectable workflows:

- Local OCR.
- AI OCR.
- Hybrid OCR.

Detect and extract:

- Text.
- Paragraphs.
- Headings.
- Lists.
- Tables.
- Figures.
- Captions.
- Equations.
- Headers and footers.
- Footnotes.
- Page numbers.
- Mathematical expressions.

OCR results should contain text, bounding boxes, confidence information, language, reading order, and processing metadata where supported.

Support English, Burmese, and additional languages through an extensible language system.

Do not automatically perform destructive Zawgyi/Unicode conversion. Preserve original text and make conversion optional.

Provide a review interface for uncertain OCR results.

11. Element Extraction

Users must be able to select individual detected elements and copy or insert them into the document editor.

Support:

- Text extraction.
- Table extraction.
- Figure extraction.
- Equation extraction.
- Manual selection.
- Manual cropping.
- AI-assisted extraction.
- Confidence and verification indicators.

Preserve original source coordinates and references.

12. Table Reconstruction

Provide:

- Manual crop.
- Automatic table detection.
- AI-assisted reconstruction.
- Editable rows and columns.
- Cell editing.
- Merge and split.
- Borders and alignment.
- Header rows.
- Resizing.
- Original-versus-reconstructed comparison.

Never invent unreadable cell values.

Unknown or uncertain cells must be explicitly marked for review.

Preserve original table data and record proposed AI changes.

13. Figure Reconstruction

Provide:

- Manual crop.
- Smart crop.
- Image enhancement.
- AI-assisted understanding.
- Optional reconstruction.
- Label and caption editing.
- Original-versus-reconstructed comparison.

Where possible, use structured representations for shapes, labels, connections, positions, and numeric data.

Prefer deterministic SVG or structured rendering when exact labels and relationships matter.

Generative image models must not be treated as authoritative sources of original data.

Allow users to approve or reject reconstructed figures.

14. Equation Recognition and Editing

Support:

- LaTeX extraction.
- Editable equation input.
- Live preview.
- Fractions.
- Matrices.
- Integrals.
- Summations.
- Greek symbols.
- Subscripts and superscripts.
- Equation numbering.
- Original equation image preservation.
- Native Microsoft Word equations through OMML.

Validate LaTeX-to-OMML conversion and test exported equations in compatible document applications.

15. Main Document Editor

Use Tiptap as the primary editor, with a stable internal document model independent of the editor implementation.

Support:

- Headings.
- Paragraphs.
- Lists.
- Tables.
- Images.
- Captions.
- Equations.
- Footnotes.
- Links.
- Page breaks.
- Find and replace.
- Undo and redo.
- Alignment.
- Page layout.
- Headers and footers.
- Page numbering.

Support A4, Letter, custom page sizes, portrait, landscape, and configurable margins.

Extracted elements must be insertable and editable where technically possible.

16. Main Workspace UI/UX

The primary workspace should use a two-panel layout:

Left Panel

- Image picker.
- Page navigator.
- Source image viewer.
- Image processing controls.
- OCR controls.
- Extraction tools.
- AI tools.

Right Panel

- Rich Text Editor.
- Document editing tools.
- Page layout controls.
- Export actions.

Requirements:

- No permanent left navigation drawer.
- Header-based popup navigation.
- Resizable panels.
- Collapsible panels.
- Independent scrolling.
- Fullscreen source viewer.
- Fullscreen editor.
- Responsive desktop/tablet/mobile layouts.
- Adaptive single-panel mobile workflow.
- Organized tabs, popups, switches, and floating toolbars.
- Avoid overcrowded controls.

The interface should feel like a modern professional document application.

Use a polished, minimal design language with subtle Liquid Glass or glassmorphism effects where appropriate.

Do not overuse blur or decorative elements.

Important Design Instruction

Do not prescribe fixed UI values in this specification.

Do not hardcode arbitrary colors, font sizes, dimensions, spacing, margins, padding, radii, or blur values.

The implementation agent must evaluate the application's design system, component hierarchy, responsiveness, accessibility, and visual balance before choosing values.

Create consistent design tokens and reusable components.

The application should support user customization of:

- Light/Dark/System themes.
- Accent colors.
- Custom color picker.
- Application font family.
- Font size.
- Font import where supported.
- Blur intensity.
- Border radius or visual style.
- Animation preferences.
- Reduced motion.
- UI density.

Keep application UI typography independent from exported document typography.

17. History and Recovery

Support:

- Document revisions.
- Processing history.
- AI task history.
- Image processing versions.
- Export history.
- Selective deletion.
- Version comparison.
- Restore.
- Autosave.
- Backup and recovery.

Keep editor undo/redo separate from document revision history.

18. Local Database and Storage

Use a local SQLite architecture.

Recommended approach:

- Application-level SQLite database for global settings and project registry.
- Individual project-level SQLite database for project-specific information.
- Local project asset directories.
- Relative asset references for portability.
- Project manifest.
- Project backups.
- Database migrations.
- Integrity checks.
- Transactional operations.

Consider tables for:

- projects.
- documents.
- pages.
- assets.
- elements.
- element_versions.
- ocr_results.
- layout_regions.
- ai_tasks.
- ai_task_results.
- ai_providers.
- ai_models.
- document_versions.
- history_events.
- exports.
- jobs.
- app_settings.
- schema_migrations.

Refine the schema based on actual requirements.

Do not store API keys as plaintext database values.

Do not rely on SQLite files being safely shared across arbitrary network filesystems. Use a controlled backend API for connected devices.

19. Project Structure

Design a modular monorepo.

Consider:

- apps/web
- apps/desktop
- backend/app
- packages/shared-types
- packages/document-schema
- packages/api-contracts
- packages/design-tokens
- docs
- tests
- scripts

Provide a clear directory tree and explain module responsibilities.

Avoid unnecessary fragmentation or excessive helper files.

20. Security and Privacy

- No mandatory cloud accounts.
- No third-party cloud database.
- No mandatory cloud storage.
- Explicit consent before sending content to external AI providers.
- Secure credential storage.
- No API keys in frontend code or logs.
- File type and path validation.
- Safe PDF and archive handling.
- Proper backend access control.
- Secure local-network pairing if supported.
- No public backend exposure by default.
- No unnecessary telemetry.

Clearly explain which operations are fully local and which transmit data externally.

21. Development Roadmap

Create a phased implementation roadmap:

Phase 0 — Foundation and Architecture.

Phase 1 — Local Storage and Project Management.

Phase 2 — Main UI and Workspace.

Phase 3 — Import and Image Processing.

Phase 4 — Local OCR and Layout Detection.

Phase 5 — Element Extraction.

Phase 6 — AI Integration and Free Usage First.

Phase 7 — Advanced Table, Figure, and Equation Reconstruction.

Phase 8 — Document Editor and Export.

Phase 9 — History, Backup, and Recovery.

Phase 10 — Desktop, PWA, and Mobile Distribution.

Phase 11 — Final QA and Production Release.

For every phase, specify:

- Objectives.
- Features.
- Technical tasks.
- Dependencies.
- Expected deliverables.
- Testing requirements.
- Completion criteria.

Development must be phased. Do not skip ahead while foundational functionality remains incomplete.

22. Accuracy and Quality Assurance

Define benchmarks for:

- English OCR.
- Burmese OCR.
- Mixed-language OCR.
- Damaged or old book pages.
- Mathematical equations.
- Tables.
- Multi-column layouts.
- Camera photographs.
- Scanned PDFs.
- Mixed PDFs.

Include appropriate metrics such as:

- Character Error Rate.
- Word Error Rate.
- Table cell accuracy.
- Equation recognition accuracy.
- Layout detection accuracy.
- Reading order accuracy.

Keep original values, AI proposals, differences, provider/model information, timestamps, and verification status.

Possible statuses:

- Pending.
- Verified.
- Rejected.
- Needs Review.
- Uncertain.

AI confidence scores must not be presented as guarantees.

23. Production Readiness

Define final acceptance criteria for:

- Stable architecture.
- Local data reliability.
- OCR workflows.
- Manual extraction.
- AI-assisted extraction.
- Free/local AI functionality.
- Optional paid provider integrations.
- Dynamic model management.
- Editable text, tables, figures, and equations.
- DOCX and TXT export.
- History and recovery.
- Desktop distribution.
- Supported PWA functionality.
- Security.
- Performance.
- Documentation.
- Installation and release procedures.

24. Final Instructions

Make the specification technically realistic.

Identify limitations, dependencies, risks, and alternative solutions instead of promising unsupported functionality.

Preserve all explicitly selected product decisions.

Where multiple approaches are possible, compare them and recommend the most maintainable solution.

Do not introduce unnecessary paid services or cloud dependencies.

Do not reduce the product to a basic OCR application.

Do not omit important features simply because they are technically challenging. Instead, place them in an appropriate development phase and document their requirements.

The resulting "Prompt.md" must be sufficiently detailed that another AI coding agent can understand the complete product vision and implement it phase by phase without repeatedly asking for the original requirements.

Create "Prompt.md" only. Do not begin application implementation during this task.

Additional Core Requirement: Adaptive Background Processing & Resource Management

This is a mandatory architectural requirement for DocuRebuild.

The application must work smoothly across a wide range of hardware, including low-end computers and devices with limited RAM, CPU performance, storage, and battery capacity.

Do not assume users have high-end hardware.

1. Background Processing Architecture

Move resource-intensive operations away from the main UI thread.

This includes:

- OCR.
- PDF rendering and extraction.
- Image processing.
- Layout detection.
- Table and figure detection.
- AI processing.
- Document conversion.
- DOCX generation.
- Thumbnail generation.
- Large file importing and indexing.

Use appropriate background workers, asynchronous tasks, process isolation, or native capabilities depending on the operation.

The UI must remain responsive during processing.

2. Adaptive Resource Management

Implement an Adaptive Resource Management system.

Monitor available system information where supported:

- CPU usage.
- Memory availability and usage.
- Active background tasks.
- Processing workload.
- Battery and power-saving state where available.
- Device capability and platform limitations.

Adjust processing concurrency, batch size, image resolution, rendering quality, cache usage, and worker allocation dynamically.

Avoid aggressive resource monitoring that itself creates unnecessary overhead.

Never assume identical hardware capabilities across platforms.

3. Processing Modes

Provide user-selectable processing presets:

- Auto Adaptive.
- Battery Saver.
- Low Resource.
- Balanced.
- High Performance.

Each mode should define sensible resource-management behavior.

Auto Adaptive should be the default unless a platform-specific reason requires otherwise.

Allow advanced users to customize meaningful resource settings.

Do not hardcode arbitrary CPU or RAM thresholds without technical justification. Use capability detection, safe defaults, runtime feedback, and platform-aware resource policies.

4. Task Queue and Scheduling

Implement a persistent and manageable background task queue.

Requirements:

- Task priorities.
- Configurable concurrency.
- Queue management.
- Pause and resume where supported.
- Cancel tasks.
- Retry failed tasks.
- Task progress reporting.
- Error reporting.
- Task persistence and recovery after application restart.
- Avoid duplicate processing.
- Prioritize interactive user actions over non-urgent background work.

Do not run every task simultaneously.

Use bounded concurrency and resource-aware scheduling.

5. Memory and Large File Management

- Process large PDFs page by page or in controlled batches.
- Avoid loading entire large documents into memory unnecessarily.
- Use thumbnail caching and controlled cache eviction.
- Release temporary buffers and resources promptly.
- Avoid unnecessary image copies.
- Use streaming or incremental processing where practical.
- Implement configurable cache management.
- Avoid excessive preloading.
- Provide graceful behavior when memory is insufficient.

Preserve original source files regardless of processing settings.

6. UI Responsiveness

- Never block the main UI thread with heavy processing.
- Show meaningful progress and processing states.
- Keep navigation and editing responsive.
- Allow users to continue working while background tasks run when safe.
- Avoid unnecessary re-rendering.
- Use virtualized lists for large page and document collections where appropriate.
- Respect reduced-motion preferences.
- Display resource-related warnings only when useful.

7. Local AI Resource Management

Local AI models can be resource-intensive.

Provide:

- Model compatibility information where available.
- Estimated hardware requirements when reliable.
- Model loading and unloading controls.
- Optional automatic unloading after inactivity.
- Configurable local inference concurrency.
- Memory-aware model selection guidance.
- Clear warnings before loading models likely to exceed available resources.
- Graceful fallback to smaller models, external free-tier providers, or manual workflows.

Never silently switch to paid AI services.

Never automatically download large AI models without user consent.

8. Background Processing Settings

Organize user controls into sensible Basic and Advanced settings.

Include options for:

- Processing mode.
- Background task behavior.
- Task concurrency.
- Processing priority.
- Cache management.
- Memory optimization.
- Image processing quality.
- PDF rendering quality.
- Local AI resource usage.
- Automatic model unloading.
- Power-saving behavior.

Expose only settings that are genuinely supported by the platform and implementation.

9. Cross-Platform Considerations

Desktop, browser/PWA, and mobile environments have different background execution limitations.

Do not assume browser tabs or mobile operating systems can run unlimited background tasks.

Document platform-specific limitations and provide appropriate fallbacks.

For mobile, prefer foreground processing or controlled background execution when required by the operating system.

10. Acceptance Criteria

- Heavy operations do not freeze the UI.
- Large PDFs can be processed incrementally.
- Background task concurrency is bounded.
- Users can monitor, pause, cancel, and recover supported tasks.
- Low-resource devices can use the core application.
- Memory usage remains controlled.
- Local AI does not overload the device without warning.
- Processing behavior adapts to available resources.
- All processing modes produce correct results; performance modes must not silently compromise document accuracy.
- Original source content is never destroyed by resource optimization.

Design this as a core platform service, not as isolated optimizations added independently to each feature.

Additional Product Requirements: GitHub Integration, Backup & Multilingual Support

Extend the DocuRebuild product specification with the following mandatory requirements.

1. GitHub Repository Integration

DocuRebuild must support integration with the user's existing GitHub repository.

The user will provide an existing repository URL before development begins.

Prepare the architecture and development workflow to use that supplied repository directly.

Do not assume a new repository needs to be created.

Repository Connection

Support:

- Existing GitHub repository URL.
- Repository validation.
- Remote connection verification.
- Branch detection.
- Repository status inspection.
- Authentication and permission checks.
- Remote synchronization status.

The repository URL should be configurable rather than hardcoded into application source code.

If GitHub authentication is required, use an appropriate secure authentication method. Never store access tokens in plaintext or expose them to frontend code.

GitHub-assisted Development

Provide an integration strategy that allows the development agent and, where appropriate, the application to work with:

- Repository inspection.
- Commit history.
- Branches.
- Commit creation.
- Push and pull.
- Synchronization.
- Issues.
- Pull requests.
- Releases.
- Tags.
- Changelogs.
- Documentation updates.

Distinguish between Git operations performed by the development agent and GitHub features exposed inside the finished application.

Do not add unnecessary GitHub functionality to the application's main UI if it does not benefit end users.

2. GitHub Backup and Recovery System

GitHub should provide an additional backup location for application source code and project documentation.

However, user-generated documents and imported source materials must remain private and local by default.

Backup Categories

Separate backup into clearly defined categories:

A. Source Code Backup

- Application source code.
- Configuration templates without secrets.
- Tests.
- Scripts.
- Development documentation.

B. Documentation Backup

- Architecture documentation.
- Database documentation.
- API documentation.
- User guides.
- Changelogs.
- Development notes.

C. User Data Backup

- Project databases.
- Imported PDFs and images.
- Reconstructed documents.
- Exported DOCX/TXT files.
- AI task history.
- User settings and other personal data.

Category C must NOT be uploaded to GitHub automatically.

If users later want cloud backup of personal data, design it as a separate explicit opt-in feature with privacy warnings, encryption considerations, and repository visibility checks. Do not treat an ordinary GitHub repository as secure private document storage.

Backup Features

Consider:

- Manual backup.
- Optional scheduled source-code synchronization.
- Backup status.
- Last successful backup.
- Commit history.
- Backup verification.
- Restore from repository.
- Recovery guidance.
- Conflict detection.
- Local changes detection.
- Safe synchronization.

Never silently discard local changes.

Never force-push or rewrite remote history automatically.

Require confirmation for destructive operations and explain their consequences.

Repository Safety

Before the first synchronization:

1. Inspect the existing repository.
2. Identify its default branch and existing structure.
3. Check whether the local project already contains Git history.
4. Detect existing remote content and potential conflicts.
5. Review ".gitignore".
6. Ensure local databases, user files, credentials, caches, generated binaries, and sensitive information are excluded.
7. Present the synchronization plan when important changes are involved.

Preserve the existing repository and its history.

Do not replace the repository with a newly initialized project.

3. Multilingual Web Application

Internationalization must be part of the initial architecture, not an afterthought.

Supported Languages

Primary language: English.

Secondary language: Burmese (Myanmar).

Additional languages should be supported through an extensible localization system.

Language Requirements

- English must be the default language for new installations.
- Users can switch between English and Burmese.
- Remember the selected language.
- Support language switching without unnecessary restarts.
- All application interface text must use localization resources.
- Avoid hardcoded frontend user-facing strings.
- Include localized validation messages, errors, tooltips, dialogs, notifications, empty states, and accessibility labels.
- Support Burmese Unicode input and rendering.
- Use appropriate fonts and fallbacks for both scripts.
- Avoid text clipping, overflow, and layout assumptions based on English text length.
- Support locale-aware dates, numbers, and formatting.
- Keep source content and document content independent from application interface language.

Translation Architecture

Use a maintainable localization structure with separate language resources.

Organize translations by feature or module where appropriate.

Avoid duplicating application logic between languages.

Ensure that adding another language does not require changing core application functionality.

English should remain the canonical fallback when a translation is missing.

Do not automatically translate user-created documents or OCR content when changing the application language.

4. UI Settings Integration

Add a Language setting to the application's general appearance/preferences settings.

Allow the user to select:

- English.
- Burmese.
- System language where supported.

English remains the default fallback.

Ensure the language selector follows the same reusable design system as other settings.

5. Testing and Acceptance Criteria

GitHub

- Existing repository URL can be validated.
- Existing repository history is preserved.
- Authentication failures are handled safely.
- Local changes and remote conflicts are detected.
- Sensitive files are excluded from commits.
- Backup status can be verified.
- Restore operations do not silently overwrite user work.
- Destructive operations require explicit approval.

Internationalization

- English is the initial default.
- Burmese translations cover all major application screens.
- Language switching works correctly.
- Burmese Unicode displays and inputs correctly.
- Layouts remain usable with longer translated strings.
- Missing translations fall back to English.
- User document content is not altered when the application language changes.

Integrate these requirements into the architecture, UI design, database/settings model, development roadmap, testing strategy, and final production acceptance criteria.

This is GitHub Repository Url for this project: "https://github.com/minkhantthu2692-gif/DocuRebuild.git"

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