import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import type { Content } from "@tiptap/core";
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Captions,
  CaseSensitive,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  CircleAlert,
  Code2,
  Download,
  FileText,
  History,
  Italic,
  List,
  ListOrdered,
  Link2,
  Quote,
  Redo2,
  Search,
  Sigma,
  SquareFunction,
  Strikethrough,
  Type,
  Underline as UnderlineIcon,
  Undo2,
  X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { DocumentRecord, JSONContent } from "@docurebuild/shared-types";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useAppSettings, useUpdateSettings } from "@/hooks/use-app";
import { useDocument, useSaveDocument } from "@/hooks/use-document";
import { api } from "@/lib/api";
import { createEditorExtensions } from "@/lib/editor-extensions";
import {
  equationAt,
  equationContent,
  renderEquationPreview,
  selectedEquation,
  type EquationKind,
  type SelectedEquation,
} from "@/lib/editor-equation";
import { figureInsertionContent, figureAt, selectedFigure, type SelectedFigure } from "@/lib/editor-figure";
import { findMatches } from "@/lib/editor-search";
import { resolveLocale } from "@/lib/format";
import { normalizeLinkUrl } from "@/lib/link";
import { ocrInsertionContent } from "@/lib/ocr-insertion";
import { countCharacters, countWords } from "@/lib/text";
import { cn } from "@/lib/utils";
import { EditorTableMenu } from "./editor-table-menu";
import { RevisionDialog } from "./revision-dialog";
import { useWorkspaceActions } from "./workspace-actions-context";

const EMPTY_DOCUMENT: Content = {
  type: "doc",
  content: [{ type: "paragraph" }],
};

const AUTOSAVE_DELAY_MS = 900;

interface EditorPanelProps {
  projectId: string;
  className?: string;
}

interface ToolbarButtonProps {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}

function ToolbarButton({ label, icon: Icon, onClick, active, disabled }: ToolbarButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={active ? "secondary" : "ghost"}
          size="icon-xs"
          aria-label={label}
          aria-pressed={active}
          disabled={disabled}
          onClick={onClick}
        >
          <Icon />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function blockValue(editor: Editor): string {
  if (editor.isActive("heading", { level: 1 })) return "h1";
  if (editor.isActive("heading", { level: 2 })) return "h2";
  if (editor.isActive("heading", { level: 3 })) return "h3";
  return "p";
}

export function EditorPanel({ projectId, className }: EditorPanelProps) {
  const { t, i18n } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.resolvedLanguage);

  const documentQuery = useDocument(projectId);
  const settingsQuery = useAppSettings();
  const updateSettings = useUpdateSettings();
  const errorMessage = useApiErrorMessage();
  const { mutateAsync: saveDocument, isPending: isSaving } = useSaveDocument(projectId);
  const { insertion, consumeInsertion } = useWorkspaceActions();

  const [initialized, setInitialized] = useState(false);
  const [revision, setRevision] = useState(0);
  const [savedRevision, setSavedRevision] = useState(0);
  const [plainText, setPlainText] = useState("");
  const [saveError, setSaveError] = useState(false);
  const [exporting, setExporting] = useState<"markdown" | "txt" | "docx" | null>(
    null,
  );
  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState("");
  const [replaceQuery, setReplaceQuery] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [activeMatch, setActiveMatch] = useState(0);
  const findInputRef = useRef<HTMLInputElement>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const [linkError, setLinkError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [figureSelection, setFigureSelection] = useState<SelectedFigure | null>(null);
  const [figureOpen, setFigureOpen] = useState(false);
  const [figureCaption, setFigureCaption] = useState("");
  const [figureAlt, setFigureAlt] = useState("");
  const [figureNumbered, setFigureNumbered] = useState(false);
  const [equationSelection, setEquationSelection] = useState<SelectedEquation | null>(null);
  const [equationOpen, setEquationOpen] = useState(false);
  const [equationLatex, setEquationLatex] = useState("");
  const [equationNumbered, setEquationNumbered] = useState(false);
  // Used when inserting; an edited equation takes its kind from the node.
  const [equationKind, setEquationKind] = useState<EquationKind>("block");

  const revisionRef = useRef(0);
  const savedRevisionRef = useRef(0);
  // Saves are serialized so an older request can never overwrite newer content.
  const saveChainRef = useRef<Promise<boolean>>(Promise.resolve(true));
  const latestContent = useRef<JSONContent | null>(null);
  const latestText = useRef("");

  const placeholderRef = useRef("");
  placeholderRef.current = t("editor.placeholder");
  const editorLabelRef = useRef("");
  editorLabelRef.current = t("document");

  const editor = useEditor({
    extensions: createEditorExtensions(() => placeholderRef.current),
    content: EMPTY_DOCUMENT,
    editable: false,
    editorProps: {
      attributes: {
        class: "focus:outline-none",
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": editorLabelRef.current,
      },
    },
    onUpdate: ({ editor: instance }) => {
      revisionRef.current += 1;
      const text = instance.getText({ blockSeparator: "\n\n" });
      latestContent.current = instance.getJSON() as JSONContent;
      latestText.current = text;
      setPlainText(text);
      setFigureSelection(selectedFigure(instance.state));
      setEquationSelection(selectedEquation(instance.state));
      setRevision(revisionRef.current);
    },
    onSelectionUpdate: ({ editor: instance }) => {
      setFigureSelection(selectedFigure(instance.state));
      setEquationSelection(selectedEquation(instance.state));
    },
  });

  useEffect(() => {
    if (!editor || initialized || !documentQuery.data) return;
    editor.commands.setContent(
      documentQuery.data.content as unknown as Content,
      { emitUpdate: false },
    );
    const text = documentQuery.data.plain_text;
    latestContent.current = documentQuery.data.content;
    latestText.current = text;
    setPlainText(text);
    // `setEditable` emits an update by default, which would mark the freshly
    // loaded document dirty and trigger an unnecessary save request.
    editor.setEditable(true, false);
    setInitialized(true);
  }, [editor, initialized, documentQuery.data]);

  useEffect(() => {
    if (!editor || !initialized) return;
    const previousLabel = editor.view.dom.getAttribute("aria-label");
    editor.view.dom.setAttribute("aria-label", t("document"));
    return () => {
      if (previousLabel !== null) editor.view.dom.setAttribute("aria-label", previousLabel);
    };
  }, [editor, initialized, t]);

  useEffect(() => {
    if (!editor || !initialized || !insertion) return;
    editor
      .chain()
      .focus("end")
      .insertContent(
        insertion.type === "text"
          ? ocrInsertionContent(insertion.text, insertion.note)
          : figureInsertionContent(insertion),
      )
      .run();
    consumeInsertion(insertion.id);
  }, [editor, initialized, insertion, consumeInsertion]);

  const saveSnapshot = useCallback(async (): Promise<boolean> => {
    if (!editor || !initialized) return true;
    const snapshot = revisionRef.current;
    if (snapshot === savedRevisionRef.current) return true;

    // Capture the exact content now; the queue may run later.
    const content = editor.getJSON() as JSONContent;
    const text = editor.getText({ blockSeparator: "\n\n" });

    const run = saveChainRef.current.then(async () => {
      // A queued save that is no longer the newest content is unnecessary.
      if (snapshot <= savedRevisionRef.current) return true;
      try {
        await saveDocument({ content, plainText: text });
        if (snapshot > savedRevisionRef.current) {
          savedRevisionRef.current = snapshot;
          setSavedRevision(snapshot);
        }
        setSaveError(false);
        return true;
      } catch {
        setSaveError(true);
        return false;
      }
    });
    saveChainRef.current = run;
    return run;
  }, [editor, initialized, saveDocument]);

  const exportDocument = useCallback(
    async (format: "markdown" | "txt" | "docx") => {
      if (!editor || !initialized || exporting) return;
      setExporting(format);
      try {
        // Never export stale content: the download must reflect what is on screen.
        const saved = await saveSnapshot();
        if (!saved) {
          toast.error(t("export.saveFailed"));
          return;
        }
        const link = document.createElement("a");
        link.href = api.documentExportUrl(projectId, format);
        link.rel = "noopener";
        link.download = "";
        document.body.appendChild(link);
        link.click();
        link.remove();
        toast.success(t(`export.started.${format}`));
      } finally {
        setExporting(null);
      }
    },
    [editor, initialized, exporting, saveSnapshot, projectId, t],
  );

  const matches = useMemo(() => {
    // `revision` changes on every document edit, which refreshes stale ranges.
    void revision;
    return editor ? findMatches(editor.state.doc, findQuery, matchCase) : [];
  }, [editor, findQuery, matchCase, revision]);

  const safeActiveMatch = matches.length === 0 ? 0 : Math.min(activeMatch, matches.length - 1);

  const openFind = useCallback(() => {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    if (to > from && to - from <= 200) {
      const selected = editor.state.doc.textBetween(from, to, "\n", "\n").trim();
      if (selected && !selected.includes("\n")) setFindQuery(selected);
    }
    setActiveMatch(0);
    setFindOpen(true);
  }, [editor]);

  const closeFind = useCallback(() => {
    setFindOpen(false);
  }, []);

  const stepMatch = useCallback(
    (delta: number) => {
      if (matches.length === 0) return;
      setActiveMatch((current) => {
        const next = (Math.min(current, matches.length - 1) + delta) % matches.length;
        return next < 0 ? next + matches.length : next;
      });
    },
    [matches.length],
  );

  const replaceCurrent = useCallback(() => {
    if (!editor || !editor.isEditable || matches.length === 0) return;
    const match = matches[safeActiveMatch];
    const { state, view } = editor;
    const tr = state.tr;
    if (replaceQuery) {
      // Keep the formatting of the text being replaced.
      const marks = state.doc.resolve(match.from).marks();
      tr.replaceWith(match.from, match.to, state.schema.text(replaceQuery, marks));
    } else {
      tr.delete(match.from, match.to);
    }
    view.dispatch(tr);
    editor.commands.scrollIntoView();
  }, [editor, matches, safeActiveMatch, replaceQuery]);

  const replaceAllMatches = useCallback(() => {
    if (!editor || !editor.isEditable || matches.length === 0) return;
    const { state, view } = editor;
    const tr = state.tr;
    // Replace from the end so earlier positions stay valid.
    for (let index = matches.length - 1; index >= 0; index -= 1) {
      const match = matches[index];
      if (replaceQuery) {
        const marks = state.doc.resolve(match.from).marks();
        tr.replaceWith(match.from, match.to, state.schema.text(replaceQuery, marks));
      } else {
        tr.delete(match.from, match.to);
      }
    }
    view.dispatch(tr);
    editor.commands.scrollIntoView();
    setActiveMatch(0);
    toast.success(t("editor.find.replaced", { count: matches.length }));
  }, [editor, matches, replaceQuery, t]);

  const openLinkDialog = useCallback(() => {
    if (!editor) return;
    const active = editor.isActive("link");
    const { from, to } = editor.state.selection;
    if (!active && from === to) return;
    const href = editor.getAttributes("link").href;
    const selected =
      from !== to ? editor.state.doc.textBetween(from, to, " ", " ").trim() : "";
    setLinkUrl(
      typeof href === "string" && href
        ? href
        : normalizeLinkUrl(selected)
          ? selected
          : "",
    );
    setLinkError(null);
    setLinkOpen(true);
  }, [editor]);

  const applyLink = useCallback(() => {
    if (!editor) return;
    const url = normalizeLinkUrl(linkUrl);
    if (!url) {
      setLinkError(t("editor.link.invalid"));
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    setLinkOpen(false);
  }, [editor, linkUrl, t]);

  const removeLink = useCallback(() => {
    if (!editor) return;
    editor.chain().focus().extendMarkRange("link").unsetLink().run();
    setLinkOpen(false);
  }, [editor]);

  const openFigureDialog = useCallback(() => {
    if (!editor) return;
    const figure = selectedFigure(editor.state);
    if (!figure) return;
    setFigureCaption(figure.caption);
    setFigureAlt(figure.alt);
    setFigureNumbered(figure.numbered);
    setFigureOpen(true);
  }, [editor]);

  const applyFigureCaption = useCallback(() => {
    if (!editor || !figureSelection) return;
    if (!figureAt(editor.state, figureSelection.pos)) {
      // The document changed while the dialog was open, so the stored position
      // no longer points at this figure. Never edit a different node.
      setFigureOpen(false);
      toast.error(t("editor.figure.gone"));
      return;
    }
    // Re-select the node so the edit applies to the figure that was opened,
    // even if focus moved into the dialog in the meantime.
    editor
      .chain()
      .focus()
      .setNodeSelection(figureSelection.pos)
      .updateAttributes("figure", {
        caption: figureCaption.trim(),
        alt: figureAlt.trim(),
        numbered: figureNumbered,
      })
      .run();
    setFigureOpen(false);
  }, [editor, figureSelection, figureCaption, figureAlt, figureNumbered, t]);

  const equationPreview = useMemo(
    () => renderEquationPreview(equationLatex, equationKind),
    [equationLatex, equationKind],
  );

  const openEquationDialog = useCallback(
    (kind: EquationKind) => {
      if (!editor) return;
      const selected = selectedEquation(editor.state);
      // Editing keeps the selected node's kind; a new equation uses the button.
      setEquationKind(selected?.kind ?? kind);
      setEquationLatex(selected?.latex ?? "");
      setEquationNumbered(selected?.numbered ?? false);
      setEquationOpen(true);
    },
    [editor],
  );

  const applyEquation = useCallback(() => {
    if (!editor) return;
    const latex = equationLatex.trim();
    // Invalid or empty LaTeX is never inserted; the dialog explains why.
    if (!latex || equationPreview.error) return;
    if (equationSelection) {
      if (!equationAt(editor.state, equationSelection.pos)) {
        // The document changed while the dialog was open. Never edit a node
        // that merely happens to sit at the old position now.
        setEquationOpen(false);
        toast.error(t("editor.equation.gone"));
        return;
      }
      const chain = editor.chain().focus().setNodeSelection(equationSelection.pos);
      if (equationSelection.kind === "inline") {
        chain.updateInlineMath({ latex, pos: equationSelection.pos }).run();
      } else {
        chain
          .command(({ tr }) => {
            const node = tr.doc.nodeAt(equationSelection.pos);
            if (!node || node.type.name !== "blockMath") return false;
            tr.setNodeMarkup(equationSelection.pos, undefined, {
              ...node.attrs,
              latex,
              numbered: equationNumbered,
            });
            return true;
          })
          .run();
      }
    } else {
      editor
        .chain()
        .focus()
        .insertContent(equationContent(latex, equationKind, equationNumbered))
        .run();
    }
    setEquationOpen(false);
  }, [
    editor,
    equationKind,
    equationLatex,
    equationNumbered,
    equationPreview.error,
    equationSelection,
    t,
  ]);

  const removeEquation = useCallback(() => {
    if (!editor || !equationSelection) return;
    if (!equationAt(editor.state, equationSelection.pos)) {
      setEquationOpen(false);
      toast.error(t("editor.equation.gone"));
      return;
    }
    const chain = editor.chain().focus().setNodeSelection(equationSelection.pos);
    if (equationSelection.kind === "inline") {
      chain.deleteInlineMath({ pos: equationSelection.pos }).run();
    } else {
      chain.deleteBlockMath({ pos: equationSelection.pos }).run();
    }
    setEquationOpen(false);
  }, [editor, equationSelection, t]);

  const applyRestoredDocument = useCallback(
    (record: DocumentRecord) => {
      if (!editor) return;
      editor.commands.setContent(record.content as unknown as Content, {
        emitUpdate: true,
      });
      // The backend already stored this exact version, so it is not dirty.
      // Editor undo history starts fresh here; the replaced state remains a
      // version and can be restored from the same dialog.
      savedRevisionRef.current = revisionRef.current;
      latestContent.current = record.content;
      latestText.current = record.plain_text;
      setSavedRevision(revisionRef.current);
      setPlainText(record.plain_text);
      setSaveError(false);
      editor.commands.focus();
    },
    [editor],
  );

  useEffect(() => {
    if (!findOpen) return;
    findInputRef.current?.focus();
    findInputRef.current?.select();
  }, [findOpen]);

  useEffect(() => {
    if (!findOpen || !editor || matches.length === 0) return;
    const match = matches[safeActiveMatch];
    editor.commands.setTextSelection({ from: match.from, to: match.to });
    editor.commands.scrollIntoView();
  }, [findOpen, editor, matches, safeActiveMatch]);

  useEffect(() => {
    const handleFindKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        if (findOpen) findInputRef.current?.focus();
        else openFind();
      }
    };
    window.addEventListener("keydown", handleFindKeyDown);
    return () => window.removeEventListener("keydown", handleFindKeyDown);
  }, [findOpen, openFind]);

  useEffect(() => {
    const handleLinkKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "k") return;
      // Never reopen (and reset) the dialog while it is already being edited.
      if (linkOpen || !editor?.isEditable) return;
      event.preventDefault();
      openLinkDialog();
    };
    window.addEventListener("keydown", handleLinkKeyDown);
    return () => window.removeEventListener("keydown", handleLinkKeyDown);
  }, [editor, linkOpen, openLinkDialog]);

  useEffect(() => {
    if (!editor || !initialized || revision === savedRevision) return;
    const timer = window.setTimeout(() => {
      void saveSnapshot();
    }, AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [editor, initialized, revision, savedRevision, saveSnapshot]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveSnapshot();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [saveSnapshot]);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (revisionRef.current > savedRevisionRef.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  // Best-effort flush when leaving the workspace inside the SPA.
  useEffect(() => {
    return () => {
      if (revisionRef.current > savedRevisionRef.current && latestContent.current) {
        void api
          .saveDocument(projectId, latestContent.current, latestText.current)
          .catch(() => undefined);
      }
    };
  }, [projectId]);

  const wordCount = useMemo(() => countWords(plainText, locale), [plainText, locale]);
  const characterCount = useMemo(() => countCharacters(plainText), [plainText]);

  const documentFont = settingsQuery.data?.editor.document_font ?? "serif";
  const fontFamily =
    documentFont === "sans" ? "var(--font-document-sans)" : "var(--font-document)";

  const dirty = revision !== savedRevision;

  const formattedBlock = editor ? blockValue(editor) : "p";
  const linkEnabled = Boolean(
    editor?.isEditable &&
      (editor.isActive("link") || !editor.state.selection.empty),
  );

  return (
    <section className={cn("flex h-full min-h-0 flex-col bg-background/20", className)}>
      <header className="flex h-panel shrink-0 items-center gap-2 border-b border-border/60 bg-background/35 px-3">
        <FileText className="size-icon-sm text-muted-foreground" aria-hidden="true" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("document")}
        </h2>

        <div className="ml-auto flex items-center gap-1.5">
          <div className="flex items-center gap-1.5 text-2xs text-muted-foreground" role="status" aria-live="polite">
            {saveError ? (
              <button
                type="button"
                className="focus-ring flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-destructive transition-colors hover:bg-destructive/10"
                onClick={() => void saveSnapshot()}
              >
                <CircleAlert className="size-3.5" />
                <span>{t("save.failed")}</span>
                <span className="font-medium underline underline-offset-2">{t("save.retry")}</span>
              </button>
            ) : isSaving ? (
              <>
                <Spinner className="size-3.5" />
                <span>{t("save.saving")}</span>
              </>
            ) : dirty ? (
              <>
                <Circle className="size-3.5 text-warning" />
                <span>{t("save.unsaved")}</span>
              </>
            ) : (
              <>
                <Check className="size-3.5 text-success" />
                <span>{t("save.saved")}</span>
              </>
            )}
          </div>

          <Separator orientation="vertical" className="h-5" />

          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t("revisions.open")}
            disabled={!editor || !initialized}
            onClick={() => setHistoryOpen(true)}
          >
            <History />
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t("export.label")}
                disabled={!editor || !initialized || exporting !== null}
              >
                {exporting ? <Spinner /> : <Download />}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{t("export.label")}</DropdownMenuLabel>
              <DropdownMenuItem
                onSelect={() => void exportDocument("markdown")}
                className="flex-col items-start gap-0.5"
              >
                <span>{t("export.markdown")}</span>
                <span className="text-2xs text-muted-foreground">
                  {t("export.markdownHint")}
                </span>
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => void exportDocument("txt")}
                className="flex-col items-start gap-0.5"
              >
                <span>{t("export.txt")}</span>
                <span className="text-2xs text-muted-foreground">{t("export.txtHint")}</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => void exportDocument("docx")}
                className="flex-col items-start gap-0.5"
              >
                <span>{t("export.docx")}</span>
                <span className="text-2xs text-muted-foreground">{t("export.docxHint")}</span>
              </DropdownMenuItem>
              <DropdownMenuLabel className="max-w-64 whitespace-normal text-2xs font-normal leading-relaxed text-muted-foreground">
                {t("export.note")}
              </DropdownMenuLabel>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t("editor.documentSettings")}
              >
                <Type />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{t("editor.typeface")}</DropdownMenuLabel>
              {(["serif", "sans"] as const).map((font) => (
                <DropdownMenuItem
                  key={font}
                  onSelect={() =>
                    updateSettings.mutate(
                      { editor: { document_font: font } },
                      { onError: (error) => toast.error(errorMessage(error)) },
                    )
                  }
                  className="justify-between"
                >
                  <span className={font === "serif" ? "font-document" : "font-ui"}>
                    {t(`editor.${font}`)}
                  </span>
                  {documentFont === font ? <Check className="text-primary" /> : null}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-0.5 border-b border-border/60 bg-background/30 px-2 py-1.5">
        <ToolbarButton
          label={t("editor.undo")}
          icon={Undo2}
          disabled={!editor?.can().undo()}
          onClick={() => editor?.chain().focus().undo().run()}
        />
        <ToolbarButton
          label={t("editor.redo")}
          icon={Redo2}
          disabled={!editor?.can().redo()}
          onClick={() => editor?.chain().focus().redo().run()}
        />

        <Separator orientation="vertical" className="mx-1 h-5" />

        <Select
          value={formattedBlock}
          disabled={!editor?.isEditable}
          onValueChange={(value) => {
            if (!editor) return;
            const chain = editor.chain().focus();
            if (value === "p") {
              chain.setParagraph().run();
            } else {
              chain
                .setHeading({ level: Number(value.slice(1)) as 1 | 2 | 3 })
                .run();
            }
          }}
        >
          <SelectTrigger
            className="h-control-xs w-28 border-transparent bg-transparent px-2 text-xs shadow-none"
            aria-label={t("editor.format")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="p">{t("editor.paragraph")}</SelectItem>
            <SelectItem value="h1">{t("editor.heading1")}</SelectItem>
            <SelectItem value="h2">{t("editor.heading2")}</SelectItem>
            <SelectItem value="h3">{t("editor.heading3")}</SelectItem>
          </SelectContent>
        </Select>

        <Separator orientation="vertical" className="mx-1 h-5" />

        <ToolbarButton
          label={t("editor.bold")}
          icon={Bold}
          active={editor?.isActive("bold")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleBold().run()}
        />
        <ToolbarButton
          label={t("editor.italic")}
          icon={Italic}
          active={editor?.isActive("italic")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleItalic().run()}
        />
        <ToolbarButton
          label={t("editor.underline")}
          icon={UnderlineIcon}
          active={editor?.isActive("underline")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleUnderline().run()}
        />
        <ToolbarButton
          label={t("editor.strike")}
          icon={Strikethrough}
          active={editor?.isActive("strike")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleStrike().run()}
        />
        <ToolbarButton
          label={editor?.isActive("link") ? t("editor.link.edit") : t("editor.link.open")}
          icon={Link2}
          active={editor?.isActive("link")}
          disabled={!linkEnabled}
          onClick={openLinkDialog}
        />

        <Separator orientation="vertical" className="mx-1 h-5" />

        <ToolbarButton
          label={t("editor.bulletList")}
          icon={List}
          active={editor?.isActive("bulletList")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleBulletList().run()}
        />
        <ToolbarButton
          label={t("editor.orderedList")}
          icon={ListOrdered}
          active={editor?.isActive("orderedList")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleOrderedList().run()}
        />
        <ToolbarButton
          label={t("editor.quote")}
          icon={Quote}
          active={editor?.isActive("blockquote")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleBlockquote().run()}
        />
        <ToolbarButton
          label={t("editor.code")}
          icon={Code2}
          active={editor?.isActive("codeBlock")}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().toggleCodeBlock().run()}
        />

        <EditorTableMenu editor={editor} />

        <ToolbarButton
          label={t("editor.figure.edit")}
          icon={Captions}
          disabled={!editor?.isEditable || !figureSelection}
          onClick={openFigureDialog}
        />

        <ToolbarButton
          label={t("editor.equation.label")}
          icon={Sigma}
          active={equationSelection?.kind === "block"}
          disabled={!editor?.isEditable}
          onClick={() => openEquationDialog("block")}
        />

        <ToolbarButton
          label={t("editor.equation.inlineLabel")}
          icon={SquareFunction}
          active={equationSelection?.kind === "inline"}
          disabled={!editor?.isEditable}
          onClick={() => openEquationDialog("inline")}
        />

        <Separator orientation="vertical" className="mx-1 h-5" />

        <ToolbarButton
          label={t("editor.alignLeft")}
          icon={AlignLeft}
          active={editor?.isActive({ textAlign: "left" })}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().setTextAlign("left").run()}
        />
        <ToolbarButton
          label={t("editor.alignCenter")}
          icon={AlignCenter}
          active={editor?.isActive({ textAlign: "center" })}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().setTextAlign("center").run()}
        />
        <ToolbarButton
          label={t("editor.alignRight")}
          icon={AlignRight}
          active={editor?.isActive({ textAlign: "right" })}
          disabled={!editor?.isEditable}
          onClick={() => editor?.chain().focus().setTextAlign("right").run()}
        />

        <Separator orientation="vertical" className="mx-1 h-5" />

        <ToolbarButton
          label={t("editor.find.open")}
          icon={Search}
          active={findOpen}
          disabled={!editor}
          onClick={() => (findOpen ? closeFind() : openFind())}
        />
      </div>

      {findOpen ? (
        <div
          role="search"
          aria-label={t("editor.find.open")}
          className="flex flex-wrap items-center gap-1.5 border-b border-border/60 bg-background/40 px-2 py-1.5"
        >
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              ref={findInputRef}
              value={findQuery}
              onChange={(event) => {
                setFindQuery(event.target.value);
                setActiveMatch(0);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  stepMatch(event.shiftKey ? -1 : 1);
                } else if (event.key === "Escape") {
                  event.preventDefault();
                  closeFind();
                  editor?.commands.focus();
                }
              }}
              placeholder={t("editor.find.placeholder")}
              aria-label={t("editor.find.placeholder")}
              className="h-control-xs w-44 pl-7 text-xs"
            />
          </div>

          <span
            className="min-w-16 text-2xs text-muted-foreground"
            role="status"
            aria-live="polite"
          >
            {findQuery
              ? matches.length > 0
                ? t("editor.find.result", {
                    current: safeActiveMatch + 1,
                    total: matches.length,
                  })
                : t("editor.find.noResults")
              : null}
          </span>

          <Button
            variant={matchCase ? "secondary" : "ghost"}
            size="icon-xs"
            aria-pressed={matchCase}
            aria-label={t("editor.find.matchCase")}
            onClick={() => {
              setMatchCase((value) => !value);
              setActiveMatch(0);
            }}
          >
            <CaseSensitive />
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t("editor.find.previous")}
            disabled={matches.length === 0}
            onClick={() => stepMatch(-1)}
          >
            <ChevronUp />
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t("editor.find.next")}
            disabled={matches.length === 0}
            onClick={() => stepMatch(1)}
          >
            <ChevronDown />
          </Button>

          <Separator orientation="vertical" className="mx-0.5 h-4" />

          <Input
            value={replaceQuery}
            onChange={(event) => setReplaceQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                replaceCurrent();
              } else if (event.key === "Escape") {
                event.preventDefault();
                closeFind();
                editor?.commands.focus();
              }
            }}
            placeholder={t("editor.find.replacePlaceholder")}
            aria-label={t("editor.find.replacePlaceholder")}
            className="h-control-xs w-44 text-xs"
          />
          <Button
            variant="outline"
            size="sm"
            disabled={!editor?.isEditable || matches.length === 0}
            onClick={replaceCurrent}
          >
            {t("editor.find.replace")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={!editor?.isEditable || matches.length === 0}
            onClick={replaceAllMatches}
          >
            {t("editor.find.replaceAll")}
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            className="ml-auto"
            aria-label={t("editor.find.close")}
            onClick={() => {
              closeFind();
              editor?.commands.focus();
            }}
          >
            <X />
          </Button>
        </div>
      ) : null}

      <div className="scrollbar-thin flex-1 overflow-y-auto bg-muted/25 px-4 py-5 sm:px-6">
        <div
          className="doc-page mx-auto w-full max-w-page rounded-lg border border-border/70 bg-card px-5 py-7 text-card-foreground shadow-md sm:px-10 sm:py-9"
          style={{ fontFamily }}
        >
          {initialized && editor ? (
            <EditorContent editor={editor} className="doc-content" />
          ) : documentQuery.isError ? (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
              <CircleAlert className="size-icon-lg text-destructive" />
              <div className="space-y-1">
                <p className="text-sm font-semibold">{t("editor.loadError.title")}</p>
                <p className="max-w-sm text-xs text-muted-foreground">
                  {t("editor.loadError.description")}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void documentQuery.refetch()}
              >
                {tCommon("actions.retry")}
              </Button>
            </div>
          ) : (
            <div className="space-y-3" aria-busy="true">
              <span className="sr-only">{tCommon("loading")}</span>
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-4/5" />
              <Skeleton className="mt-6 h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          )}
        </div>
      </div>

      <footer className="flex h-panel shrink-0 items-center gap-3 border-t border-border/60 bg-background/35 px-3 text-2xs text-muted-foreground">
        <span>{tCommon("units.words", { count: wordCount })}</span>
        <span>{tCommon("units.characters", { count: characterCount })}</span>
        <span className="ml-auto hidden sm:inline">{t("autosave")}</span>
      </footer>

      <Dialog
        open={linkOpen}
        onOpenChange={(open) => {
          setLinkOpen(open);
          if (!open) setLinkError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("editor.link.title")}</DialogTitle>
            <DialogDescription>{t("editor.link.description")}</DialogDescription>
          </DialogHeader>
          <form
            className="mt-5 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              applyLink();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="editor-link-url">{t("editor.link.url")}</Label>
              <Input
                id="editor-link-url"
                autoFocus
                value={linkUrl}
                placeholder={t("editor.link.placeholder")}
                aria-invalid={Boolean(linkError)}
                aria-describedby={linkError ? "editor-link-error" : undefined}
                onChange={(event) => {
                  setLinkUrl(event.target.value);
                  setLinkError(null);
                }}
              />
              {linkError ? (
                <p id="editor-link-error" role="alert" className="text-2xs text-destructive">
                  {linkError}
                </p>
              ) : null}
            </div>
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("editor.link.note")}
            </p>
            <DialogFooter>
              {editor?.isActive("link") ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="mr-auto"
                  onClick={removeLink}
                >
                  {t("editor.link.remove")}
                </Button>
              ) : null}
              <Button type="button" variant="outline" onClick={() => setLinkOpen(false)}>
                {tCommon("actions.cancel")}
              </Button>
              <Button type="submit">{t("editor.link.apply")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={figureOpen} onOpenChange={setFigureOpen}>
        <DialogContent className="max-w-lg">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              applyFigureCaption();
            }}
          >
            <DialogHeader>
              <DialogTitle>{t("editor.figure.title")}</DialogTitle>
              <DialogDescription>{t("editor.figure.description")}</DialogDescription>
            </DialogHeader>

            <div className="mt-4 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="figure-caption">{t("editor.figure.caption")}</Label>
                <Input
                  id="figure-caption"
                  value={figureCaption}
                  onChange={(event) => setFigureCaption(event.target.value)}
                  placeholder={t("editor.figure.captionPlaceholder")}
                  autoFocus
                />
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {t("editor.figure.captionHint")}
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="figure-alt">{t("editor.figure.alt")}</Label>
                <Input
                  id="figure-alt"
                  value={figureAlt}
                  onChange={(event) => setFigureAlt(event.target.value)}
                  placeholder={t("editor.figure.altPlaceholder")}
                />
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {t("editor.figure.altHint")}
                </p>
              </div>

              <label className="flex items-start gap-2 text-2xs leading-relaxed text-muted-foreground">
                <input
                  type="checkbox"
                  className="mt-0.5 size-3.5 accent-primary"
                  checked={figureNumbered}
                  onChange={(event) => setFigureNumbered(event.target.checked)}
                />
                <span>
                  <span className="block text-xs text-foreground">
                    {t("editor.figure.numbered")}
                  </span>
                  {t("editor.figure.numberedHint")}
                </span>
              </label>

              {figureSelection?.note ? (
                <div className="rounded-md border border-border/60 bg-background/50 p-2.5">
                  <p className="text-2xs font-medium text-muted-foreground">
                    {t("editor.figure.source")}
                  </p>
                  <p className="mt-0.5 whitespace-pre-wrap break-words text-xs leading-relaxed">
                    {figureSelection.note}
                  </p>
                </div>
              ) : null}

              <p className="text-2xs leading-relaxed text-muted-foreground">
                {t("editor.figure.note")}
              </p>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setFigureOpen(false)}>
                {tCommon("actions.cancel")}
              </Button>
              <Button type="submit">{t("editor.figure.apply")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={equationOpen} onOpenChange={setEquationOpen}>
        <DialogContent className="max-w-lg">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              applyEquation();
            }}
          >
            <DialogHeader>
              <DialogTitle>
                {equationSelection
                  ? t("editor.equation.editTitle")
                  : equationKind === "inline"
                    ? t("editor.equation.inlineInsertTitle")
                    : t("editor.equation.insertTitle")}
              </DialogTitle>
              <DialogDescription>
                {equationKind === "inline"
                  ? t("editor.equation.inlineDescription")
                  : t("editor.equation.description")}
              </DialogDescription>
            </DialogHeader>

            <div className="mt-4 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="equation-latex">{t("editor.equation.source")}</Label>
                <Textarea
                  id="equation-latex"
                  dir="ltr"
                  className="min-h-24 font-mono text-xs"
                  value={equationLatex}
                  onChange={(event) => setEquationLatex(event.target.value)}
                  placeholder="E = mc^2"
                  spellCheck={false}
                  autoFocus
                />
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {t("editor.equation.sourceHint")}
                </p>
              </div>

              <div className="space-y-1.5">
                <p className="text-2xs font-medium text-muted-foreground">
                  {t("editor.equation.preview")}
                </p>
                <div
                  aria-live="polite"
                  aria-label={t("editor.equation.preview")}
                  className="flex min-h-16 items-center justify-center overflow-x-auto rounded-md border border-border/60 bg-muted/20 px-3 py-2"
                >
                  {equationPreview.error ? (
                    <p role="alert" className="text-xs leading-relaxed text-destructive">
                      {t("editor.equation.invalid")}
                    </p>
                  ) : equationPreview.html ? (
                    // KaTeX output is generated locally with trust disabled, so the
                    // markup contains no links or HTML from the source.
                    <div dangerouslySetInnerHTML={{ __html: equationPreview.html }} />
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {t("editor.equation.emptyPreview")}
                    </p>
                  )}
                </div>
              </div>

              <p className="text-2xs leading-relaxed text-muted-foreground">
                {equationKind === "inline"
                  ? t("editor.equation.inlineNote")
                  : t("editor.equation.note")}
              </p>

              {equationKind === "block" ? (
                <label className="flex items-start gap-2 text-2xs leading-relaxed text-muted-foreground">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-3.5 accent-primary"
                    checked={equationNumbered}
                    onChange={(event) => setEquationNumbered(event.target.checked)}
                  />
                  <span>
                    <span className="block text-xs text-foreground">
                      {t("editor.equation.numbered")}
                    </span>
                    {t("editor.equation.numberedHint")}
                  </span>
                </label>
              ) : null}
            </div>

            <DialogFooter>
              {equationSelection ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="mr-auto"
                  onClick={removeEquation}
                >
                  {t("editor.equation.remove")}
                </Button>
              ) : null}
              <Button type="button" variant="outline" onClick={() => setEquationOpen(false)}>
                {tCommon("actions.cancel")}
              </Button>
              <Button
                type="submit"
                disabled={!equationLatex.trim() || equationPreview.error}
              >
                {equationSelection
                  ? t("editor.equation.update")
                  : equationKind === "inline"
                    ? t("editor.equation.insertInline")
                    : t("editor.equation.insert")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <RevisionDialog
        projectId={projectId}
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        currentText={plainText}
        ensureSaved={saveSnapshot}
        onRestored={applyRestoredDocument}
      />
    </section>
  );
}
