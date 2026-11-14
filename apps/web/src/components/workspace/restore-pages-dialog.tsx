import {
  ArchiveRestore,
  CircleAlert,
  FileArchive,
  FileText,
  KeyRound,
  ListChecks,
  Upload,
} from "lucide-react";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type {
  BackupSelection,
  DocumentRestoreResult,
  PageRestoreResult,
} from "@docurebuild/shared-types";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { CenteredSpinner, Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useAppMeta } from "@/hooks/use-app";
import {
  useInspectStoredBackup,
  useInspectUploadedBackup,
  useProjectBackups,
  useRestoreBackupDocument,
  useRestoreSelectedPages,
} from "@/hooks/use-projects";
import { ApiError } from "@/lib/api";
import { formatDateTime, formatFileSize, resolveLocale } from "@/lib/format";

import { useWorkspaceActions } from "./workspace-actions-context";

type BackupSource = "copy" | "upload";
type RestoreMode = "pages" | "document";
const CURRENT_DOCUMENT = "current";

interface RestorePagesDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRestored?: (result: PageRestoreResult) => void;
  onDocumentRestored?: (result: DocumentRestoreResult) => void;
}

/**
 * Copy chosen pages or a document version out of a backup.
 *
 * A full restore always creates a new project. This dialog covers the smaller
 * cases: a page was deleted or damaged, or the document needs an older version.
 * Pages are appended after the last page with new ids; a document restore
 * replaces the live document only after snapshotting the state it replaces.
 */
export function RestorePagesDialog({
  projectId,
  open,
  onOpenChange,
  onRestored,
  onDocumentRestored,
}: RestorePagesDialogProps) {
  const { t, i18n } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.language);
  const errorMessage = useApiErrorMessage();
  const metaQuery = useAppMeta();
  const backups = useProjectBackups(projectId, open);
  const inspectCopy = useInspectStoredBackup();
  const inspectUpload = useInspectUploadedBackup();
  const restore = useRestoreSelectedPages(projectId);
  const restoreDocument = useRestoreBackupDocument(projectId);
  const { restoreDocumentIntoEditor } = useWorkspaceActions();
  const inputRef = useRef<HTMLInputElement>(null);
  const passwordId = useId();

  const [mode, setMode] = useState<RestoreMode>("pages");
  const [source, setSource] = useState<BackupSource>("copy");
  const [filename, setFilename] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<BackupSelection | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [chosenDocument, setChosenDocument] = useState<string | null>(null);

  const maxMb = metaQuery.data?.max_backup_mb ?? 2048;
  const inspecting = inspectCopy.isPending || inspectUpload.isPending;
  const allSelected =
    selection !== null && chosen.size === selection.pages.length;
  const canInspect =
    source === "copy" ? filename !== "" : file !== null;

  const resetSelection = () => {
    setSelection(null);
    setChosen(new Set());
    setChosenDocument(null);
    setError(null);
  };

  const reset = () => {
    setMode("pages");
    setSource("copy");
    setFilename("");
    setFile(null);
    setPassword("");
    setValidation(null);
    resetSelection();
    if (inputRef.current) inputRef.current.value = "";
  };

  const changeOpen = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const choose = (selected: File | null) => {
    setValidation(null);
    resetSelection();
    if (!selected) {
      setFile(null);
      return;
    }
    if (!/\.(zip|drbz)$/i.test(selected.name)) {
      setFile(null);
      setValidation(t("restorePages.notArchive"));
      return;
    }
    if (selected.size > maxMb * 1024 * 1024) {
      setFile(null);
      setValidation(t("restorePages.tooLarge", { limit: maxMb }));
      return;
    }
    setFile(selected);
  };

  const adopt = (result: BackupSelection) => {
    setSelection(result);
    setChosen(new Set());
    setChosenDocument(null);
    setError(null);
  };

  const fail = (failure: unknown) => {
    setError(errorMessage(failure));
    // The staged extraction is gone, so the page and version lists are stale.
    if (failure instanceof ApiError && failure.code === "restore_selection_expired") {
      setSelection(null);
      setChosen(new Set());
      setChosenDocument(null);
    }
  };

  const inspect = () => {
    if (inspecting || !canInspect) return;
    if (source === "copy") {
      inspectCopy.mutate(
        { projectId, filename },
        { onSuccess: adopt, onError: fail },
      );
      return;
    }
    if (!file) return;
    inspectUpload.mutate(
      { projectId, file, password: password || undefined },
      { onSuccess: adopt, onError: fail },
    );
  };

  const togglePage = (pageId: string) => {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(pageId)) next.delete(pageId);
      else next.add(pageId);
      return next;
    });
  };

  const toggleAll = () => {
    if (!selection) return;
    setChosen(
      allSelected ? new Set() : new Set(selection.pages.map((page) => page.id)),
    );
  };

  const submit = () => {
    if (!selection || chosen.size === 0 || restore.isPending) return;
    restore.mutate(
      { token: selection.token, pageIds: [...chosen] },
      {
        onSuccess: (result) => {
          toast.success(t("restorePages.success", { count: result.restored }));
          changeOpen(false);
          onRestored?.(result);
        },
        onError: fail,
      },
    );
  };

  const submitDocument = () => {
    if (!selection || chosenDocument === null || restoreDocument.isPending) return;
    restoreDocument.mutate(
      {
        token: selection.token,
        revisionId: chosenDocument === CURRENT_DOCUMENT ? null : chosenDocument,
      },
      {
        onSuccess: (result) => {
          toast.success(t("restorePages.documentSuccess"));
          // The editor keeps its own working copy, so hand it the restored
          // record instead of relying on a query refetch alone.
          restoreDocumentIntoEditor(result.document);
          changeOpen(false);
          onDocumentRestored?.(result);
        },
        onError: fail,
      },
    );
  };

  const documentChosen = chosenDocument !== null;

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArchiveRestore className="size-icon-sm text-primary" aria-hidden="true" />
            {t("restorePages.title")}
          </DialogTitle>
          <DialogDescription>{t("restorePages.description")}</DialogDescription>
        </DialogHeader>

        <div className="mt-4 space-y-3">
          <div className="space-y-1.5">
            <p className="text-2xs font-medium text-muted-foreground">
              {t("restorePages.mode")}
            </p>
            <SegmentedControl
              value={mode}
              onValueChange={(value) => {
                setMode(value as RestoreMode);
                setValidation(null);
                setError(null);
              }}
              label={t("restorePages.mode")}
              options={[
                { value: "pages", label: t("restorePages.modePages") },
                { value: "document", label: t("restorePages.modeDocument") },
              ]}
            />
          </div>

          <div className="space-y-1.5">
            <p className="text-2xs font-medium text-muted-foreground">
              {t("restorePages.source")}
            </p>
            <SegmentedControl
              value={source}
              onValueChange={(value) => {
                setSource(value as BackupSource);
                resetSelection();
                setValidation(null);
              }}
              label={t("restorePages.source")}
              options={[
                { value: "copy", label: t("restorePages.sourceCopy") },
                { value: "upload", label: t("restorePages.sourceUpload") },
              ]}
            />
          </div>

          {source === "copy" ? (
            <div className="space-y-2">
              {backups.isPending ? (
                <CenteredSpinner label={t("restorePages.copiesLoading")} />
              ) : backups.isError ? (
                <p
                  role="alert"
                  className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2.5 text-2xs leading-relaxed text-destructive"
                >
                  <CircleAlert className="mt-0.5 size-icon-sm shrink-0" aria-hidden="true" />
                  <span>{t("restorePages.copiesError")}</span>
                </p>
              ) : backups.data.length === 0 ? (
                <EmptyState
                  compact
                  icon={FileArchive}
                  title={t("restorePages.emptyCopiesTitle")}
                  description={t("restorePages.noCopies")}
                />
              ) : (
                <ul className="max-h-40 space-y-1 overflow-y-auto pr-1">
                  {backups.data.map((copy) => (
                    <li key={copy.filename}>
                      <label className="flex cursor-pointer items-center gap-2.5 rounded-md border border-border/60 bg-muted/20 px-3 py-2">
                        <input
                          type="radio"
                          name="restore-pages-copy"
                          className="size-3.5 shrink-0 accent-primary"
                          checked={filename === copy.filename}
                          onChange={() => {
                            setFilename(copy.filename);
                            resetSelection();
                          }}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-xs font-medium">
                            {copy.filename}
                          </span>
                          <span className="block text-2xs text-muted-foreground">
                            {t("restorePages.copyMeta", {
                              date: formatDateTime(copy.created_at, locale),
                              size: formatFileSize(copy.byte_size, locale),
                            })}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <input
                ref={inputRef}
                type="file"
                accept=".zip,.drbz,application/zip,application/octet-stream"
                className="sr-only"
                aria-label={t("restorePages.choose")}
                onChange={(event) => choose(event.target.files?.[0] ?? null)}
              />
              <div className="rounded-lg border border-dashed border-border/80 bg-background/40 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => inputRef.current?.click()}
                  >
                    <Upload />
                    {t("restorePages.choose")}
                  </Button>
                  <span className="text-2xs text-muted-foreground">
                    {t("restorePages.limit", { limit: maxMb })}
                  </span>
                </div>
                {file ? (
                  <div className="mt-2.5 flex items-center gap-2">
                    <FileArchive
                      className="size-icon-sm shrink-0 text-primary"
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">{file.name}</p>
                      <p className="text-2xs text-muted-foreground">
                        {formatFileSize(file.size, locale)}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="mt-2.5 text-2xs text-muted-foreground">
                    {t("restorePages.noFile")}
                  </p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label
                  htmlFor={passwordId}
                  className="flex items-center gap-1.5 text-2xs"
                >
                  <KeyRound
                    className="size-icon-sm text-muted-foreground"
                    aria-hidden="true"
                  />
                  {t("restorePages.passwordOptional")}
                </Label>
                <Input
                  id={passwordId}
                  type="password"
                  autoComplete="off"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {t("restorePages.passwordHint")}
                </p>
              </div>
            </div>
          )}

          {validation ? (
            <p role="alert" className="text-2xs leading-relaxed text-destructive">
              {validation}
            </p>
          ) : null}

          {error ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2.5 text-2xs leading-relaxed text-destructive"
            >
              <CircleAlert className="mt-0.5 size-icon-sm shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </p>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="max-w-sm text-2xs leading-relaxed text-muted-foreground">
              {mode === "pages"
                ? t("restorePages.note")
                : t("restorePages.documentNote")}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!canInspect || inspecting}
              onClick={inspect}
            >
              {inspecting ? <Spinner /> : <ListChecks />}
              {inspecting ? t("restorePages.inspecting") : t("restorePages.inspect")}
            </Button>
          </div>

          {mode === "pages" && selection ? (
            <div className="rounded-lg border border-border/70 bg-background/40">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium">
                    {t("restorePages.pagesTitle")}
                  </p>
                  <p className="truncate text-2xs text-muted-foreground">
                    {t("restorePages.pagesFrom", { name: selection.source_name })}
                    {" · "}
                    {t("restorePages.pagesCount", {
                      count: selection.pages.length,
                    })}
                  </p>
                </div>
                <label className="flex items-center gap-2 text-2xs">
                  <input
                    type="checkbox"
                    className="size-3.5 shrink-0 accent-primary"
                    checked={allSelected}
                    disabled={selection.pages.length === 0}
                    onChange={toggleAll}
                  />
                  <span>{t("restorePages.selectAll")}</span>
                </label>
              </div>
              {selection.pages.length === 0 ? (
                <p className="px-3 py-4 text-2xs leading-relaxed text-muted-foreground">
                  {t("restorePages.noPages")}
                </p>
              ) : (
                <ul className="max-h-56 space-y-0.5 overflow-y-auto p-1.5">
                  {selection.pages.map((page) => (
                    <li key={page.id}>
                      <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-muted/40">
                        <input
                          type="checkbox"
                          className="size-3.5 shrink-0 accent-primary"
                          checked={chosen.has(page.id)}
                          aria-label={t("restorePages.selectPage", {
                            page: page.page_number,
                          })}
                          onChange={() => togglePage(page.id)}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-xs font-medium">
                            {t("restorePages.page", { page: page.page_number })}
                          </span>
                          <span className="block truncate text-2xs text-muted-foreground">
                            {page.original_filename || t("restorePages.unknownFile")}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          {mode === "document" && selection ? (
            <div className="rounded-lg border border-border/70 bg-background/40">
              <div className="border-b border-border/60 px-3 py-2">
                <p className="truncate text-xs font-medium">
                  {t("restorePages.documentTitle")}
                </p>
                <p className="truncate text-2xs text-muted-foreground">
                  {t("restorePages.documentFrom", {
                    name: selection.source_name,
                  })}
                  {" · "}
                  {t("restorePages.revisionCount", {
                    count: selection.document.revisions.length,
                  })}
                </p>
              </div>
              <ul className="max-h-56 space-y-0.5 overflow-y-auto p-1.5">
                <li>
                  <label className="flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 hover:bg-muted/40">
                    <input
                      type="radio"
                      name="restore-document"
                      className="mt-0.5 size-3.5 shrink-0 accent-primary"
                      checked={chosenDocument === CURRENT_DOCUMENT}
                      onChange={() => setChosenDocument(CURRENT_DOCUMENT)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-medium">
                        {t("restorePages.documentCurrent")}
                      </span>
                      <span className="block text-2xs text-muted-foreground">
                        {selection.document.current.updated_at
                          ? formatDateTime(
                              selection.document.current.updated_at,
                              locale,
                            )
                          : t("restorePages.unknownTime")}
                        {" · "}
                        {t("restorePages.characterCount", {
                          count: selection.document.current.character_count,
                        })}
                      </span>
                      <span className="mt-0.5 line-clamp-2 block text-2xs leading-relaxed text-muted-foreground">
                        {selection.document.current.preview ||
                          t("restorePages.emptyDocument")}
                      </span>
                    </span>
                  </label>
                </li>
                {selection.document.revisions.map((revision) => (
                  <li key={revision.id}>
                    <label className="flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 hover:bg-muted/40">
                      <input
                        type="radio"
                        name="restore-document"
                        className="mt-0.5 size-3.5 shrink-0 accent-primary"
                        checked={chosenDocument === revision.id}
                        onChange={() => setChosenDocument(revision.id)}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs font-medium">
                          {revision.source === "manual"
                            ? t("restorePages.revisionManual")
                            : t("restorePages.revisionAutosave")}
                        </span>
                        <span className="block text-2xs text-muted-foreground">
                          {formatDateTime(revision.created_at, locale)}
                          {" · "}
                          {t("restorePages.characterCount", {
                            count: revision.character_count,
                          })}
                        </span>
                        <span className="mt-0.5 line-clamp-2 block text-2xs leading-relaxed text-muted-foreground">
                          {revision.preview || t("restorePages.emptyDocument")}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {selection && mode === "pages" && chosen.size === 0 ? (
            <p className="text-2xs text-muted-foreground">
              {t("restorePages.noSelection")}
            </p>
          ) : null}

          {selection && mode === "document" && !documentChosen ? (
            <p className="text-2xs text-muted-foreground">
              {t("restorePages.noDocumentSelection")}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => changeOpen(false)}>
            {tCommon("actions.cancel")}
          </Button>
          {mode === "pages" ? (
            <Button
              type="button"
              disabled={!selection || chosen.size === 0 || restore.isPending}
              onClick={submit}
            >
              {restore.isPending ? <Spinner /> : <ArchiveRestore />}
              {restore.isPending
                ? t("restorePages.restoring")
                : chosen.size > 0
                  ? t("restorePages.restore", { count: chosen.size })
                  : t("restorePages.restoreIdle")}
            </Button>
          ) : (
            <Button
              type="button"
              disabled={
                !selection || !documentChosen || restoreDocument.isPending
              }
              onClick={submitDocument}
            >
              {restoreDocument.isPending ? <Spinner /> : <FileText />}
              {restoreDocument.isPending
                ? t("restorePages.restoringDocument")
                : t("restorePages.restoreDocument")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
