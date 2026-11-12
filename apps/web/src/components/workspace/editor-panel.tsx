import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import type { Content } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Check,
  Circle,
  CircleAlert,
  Code2,
  Download,
  FileText,
  Italic,
  List,
  ListOrdered,
  Quote,
  Redo2,
  Strikethrough,
  Type,
  Underline as UnderlineIcon,
  Undo2,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { JSONContent } from "@docurebuild/shared-types";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useAppSettings, useUpdateSettings } from "@/hooks/use-app";
import { useDocument, useSaveDocument } from "@/hooks/use-document";
import { api } from "@/lib/api";
import { FigureNode, figureInsertionContent } from "@/lib/editor-figure";
import { resolveLocale } from "@/lib/format";
import { ocrInsertionContent } from "@/lib/ocr-insertion";
import { countCharacters, countWords } from "@/lib/text";
import { cn } from "@/lib/utils";
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
  const [exporting, setExporting] = useState<"markdown" | "txt" | null>(null);

  const revisionRef = useRef(0);
  const savedRevisionRef = useRef(0);
  const latestContent = useRef<JSONContent | null>(null);
  const latestText = useRef("");

  const placeholderRef = useRef("");
  placeholderRef.current = t("editor.placeholder");
  const editorLabelRef = useRef("");
  editorLabelRef.current = t("document");

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        underline: {},
        link: false,
      }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      FigureNode,
      Placeholder.configure({ placeholder: () => placeholderRef.current }),
    ],
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
      setRevision(revisionRef.current);
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

    try {
      await saveDocument({
        content: editor.getJSON() as JSONContent,
        plainText: editor.getText({ blockSeparator: "\n\n" }),
      });
      savedRevisionRef.current = snapshot;
      setSavedRevision(snapshot);
      setSaveError(false);
      return true;
    } catch {
      setSaveError(true);
      return false;
    }
  }, [editor, initialized, saveDocument]);

  const exportDocument = useCallback(
    async (format: "markdown" | "txt") => {
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
      </div>

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
    </section>
  );
}
