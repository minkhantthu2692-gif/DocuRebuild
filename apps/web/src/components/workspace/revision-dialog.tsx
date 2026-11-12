import { CircleAlert, Diff, History, RotateCcw, Save } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { DocumentRecord, DocumentRevisionSummary } from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
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
import { CenteredSpinner, Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import {
  useCreateDocumentRevision,
  useDocumentRevision,
  useDocumentRevisions,
  useRestoreDocumentRevision,
} from "@/hooks/use-document";
import { formatDateTime, resolveLocale } from "@/lib/format";

import { RevisionCompare } from "./revision-compare";

interface RevisionDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Text currently shown in the editor, including unsaved changes. */
  currentText: string;
  /**
   * Persist unsaved editor state first, so the version history protects what is
   * currently on screen instead of silently replacing it.
   */
  ensureSaved: () => Promise<boolean>;
  onRestored: (document: DocumentRecord) => void;
}

/**
 * The list only carries a short preview, so the exact stored text is loaded
 * before a restore. It is read-only: restoring still replaces the whole
 * document and cannot merge a version into the current text.
 */
function RevisionPreview({
  projectId,
  revisionId,
}: {
  projectId: string;
  revisionId: string;
}) {
  const { t } = useTranslation("workspace");
  const query = useDocumentRevision(projectId, revisionId);

  return (
    <div className="mt-2 rounded-md border border-border/60 bg-background/60 p-2">
      <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        {t("revisions.previewLabel")}
      </p>
      {query.isLoading ? (
        <p className="mt-1 text-2xs text-muted-foreground">
          {t("revisions.previewLoading")}
        </p>
      ) : query.isError ? (
        <p className="mt-1 text-2xs text-warning">{t("revisions.previewError")}</p>
      ) : (
        <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-2xs leading-relaxed">
          {query.data?.plain_text.trim() || t("revisions.noText")}
        </p>
      )}
    </div>
  );
}

export function RevisionDialog({
  projectId,
  open,
  onOpenChange,
  currentText,
  ensureSaved,
  onRestored,
}: RevisionDialogProps) {
  const { t, i18n } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.language);
  const errorMessage = useApiErrorMessage();

  const query = useDocumentRevisions(projectId, open);
  const createRevision = useCreateDocumentRevision(projectId);
  const restoreRevision = useRestoreDocumentRevision(projectId);
  const [pending, setPending] = useState<DocumentRevisionSummary | null>(null);
  const [comparingId, setComparingId] = useState<string | null>(null);

  const revisions = query.data ?? [];

  const toggleCompare = (revision: DocumentRevisionSummary) => {
    setPending(null);
    setComparingId((current) => (current === revision.id ? null : revision.id));
  };

  const toggleRestore = (revision: DocumentRevisionSummary) => {
    setComparingId(null);
    setPending((current) => (current?.id === revision.id ? null : revision));
  };

  const saveVersion = async () => {
    const saved = await ensureSaved();
    if (!saved) {
      toast.error(t("revisions.saveFailed"));
      return;
    }
    try {
      await createRevision.mutateAsync();
      toast.success(t("revisions.created"));
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const restorePending = async () => {
    if (!pending) return;
    const saved = await ensureSaved();
    if (!saved) {
      toast.error(t("revisions.saveFailed"));
      return;
    }
    try {
      const record = await restoreRevision.mutateAsync(pending.id);
      onRestored(record);
      setPending(null);
      toast.success(t("revisions.restored"));
      onOpenChange(false);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setPending(null);
          setComparingId(null);
        }
        onOpenChange(next);
      }}
    >
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-2xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="size-icon-sm text-primary" aria-hidden="true" />
            {t("revisions.title")}
          </DialogTitle>
          <DialogDescription>{t("revisions.description")}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={createRevision.isPending}
            onClick={() => void saveVersion()}
          >
            {createRevision.isPending ? <Spinner /> : <Save />}
            {t("revisions.create")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            {t("revisions.refresh")}
          </Button>
          <span className="ml-auto text-2xs text-muted-foreground" role="status">
            {t("revisions.count", { count: revisions.length })}
          </span>
        </div>

        <div className="scrollbar-thin -mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          {query.isLoading ? (
            <CenteredSpinner label={t("revisions.loading")} />
          ) : query.isError ? (
            <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-xs">
              <CircleAlert
                className="mt-0.5 size-icon-sm shrink-0 text-warning"
                aria-hidden="true"
              />
              <div className="space-y-2">
                <p>{t("revisions.error")}</p>
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  {t("revisions.retry")}
                </Button>
              </div>
            </div>
          ) : revisions.length === 0 ? (
            <EmptyState
              icon={History}
              title={t("revisions.emptyTitle")}
              description={t("revisions.empty")}
              compact
            />
          ) : (
            <ul className="space-y-2">
              {revisions.map((revision) => {
                const confirming = pending?.id === revision.id;
                const comparing = comparingId === revision.id;
                return (
                  <li
                    key={revision.id}
                    className="rounded-lg border border-border/70 bg-background/45 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">
                        {t(`revisions.source.${revision.source}`)}
                      </Badge>
                      <span className="text-2xs text-muted-foreground">
                        {formatDateTime(revision.created_at, locale)}
                      </span>
                      <span className="text-2xs text-muted-foreground">
                        {tCommon("units.characters", { count: revision.character_count })}
                      </span>
                      <div className="ml-auto flex flex-wrap items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-expanded={comparing}
                          onClick={() => toggleCompare(revision)}
                        >
                          <Diff />
                          {comparing ? t("revisions.compareClose") : t("revisions.compare")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-expanded={confirming}
                          onClick={() => toggleRestore(revision)}
                        >
                          <RotateCcw />
                          {t("revisions.restore")}
                        </Button>
                      </div>
                    </div>

                    <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed text-muted-foreground">
                      {revision.preview || t("revisions.noText")}
                    </p>

                    {comparing ? (
                      <RevisionCompare
                        projectId={projectId}
                        revisionId={revision.id}
                        currentText={currentText}
                      />
                    ) : null}

                    {confirming ? (
                      <div className="mt-2 rounded-md border border-warning/40 bg-warning/5 p-2.5">
                        <p className="text-2xs leading-relaxed">
                          {t("revisions.confirm", {
                            time: formatDateTime(revision.created_at, locale),
                          })}
                        </p>
                        <RevisionPreview projectId={projectId} revisionId={revision.id} />
                        <div className="mt-2 flex flex-wrap justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setPending(null)}
                          >
                            {tCommon("actions.cancel")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={restoreRevision.isPending}
                            onClick={() => void restorePending()}
                          >
                            {restoreRevision.isPending ? <Spinner /> : <RotateCcw />}
                            {t("revisions.confirmAction")}
                          </Button>
                        </div>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <p className="rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
          {t("revisions.note")}
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
