import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Sigma, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { ElementSummary } from "@docurebuild/shared-types";

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
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/input";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useAppSettings } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { renderEquationPreview } from "@/lib/editor-equation";
import { useWorkspaceActions } from "./workspace-actions-context";

interface RegionFormulaDialogProps {
  projectId: string;
  /** The saved equation region whose reviewed text becomes the LaTeX source. */
  element: ElementSummary | null;
  pageNumber: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInserted?: () => void;
}

/**
 * Turns an extracted equation region into a real display equation.
 *
 * The stored text is only a starting point: the dialog shows the local KaTeX
 * render beside the saved crop and refuses to insert while the preview fails, so
 * a formula the user has not seen is never written into the document. The crop
 * itself stays in the project.
 */
export function RegionFormulaDialog({
  projectId,
  element,
  pageNumber,
  open,
  onOpenChange,
  onInserted,
}: RegionFormulaDialogProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const { insertEquation } = useWorkspaceActions();
  const errorMessage = useApiErrorMessage();
  const queryClient = useQueryClient();
  const settingsQuery = useAppSettings();
  const visionModel = settingsQuery.data?.ai.vision_model?.trim() ?? "";

  const [latex, setLatex] = useState("");
  const [numbered, setNumbered] = useState(false);
  const [includeNote, setIncludeNote] = useState(true);
  const [aiProposal, setAiProposal] = useState<{
    latex: string;
    model: string;
  } | null>(null);

  const transcribe = useMutation({
    mutationFn: (elementId: string) =>
      api.createAiEquationProposal(projectId, elementId),
    onSuccess: (response) => {
      setLatex(response.latex);
      setAiProposal({ latex: response.latex, model: response.model });
      toast.success(t("elements.formula.aiProposedToast"));
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => {
      // Every attempt counts against the local request limit.
      void queryClient.invalidateQueries({ queryKey: ["ai", "usage"] });
    },
  });

  useEffect(() => {
    if (!open) return;
    setLatex(element?.text ?? "");
    setNumbered(false);
    setIncludeNote(true);
    setAiProposal(null);
  }, [open, element?.id, element?.text]);

  const preview = useMemo(() => renderEquationPreview(latex, "block"), [latex]);
  const source = latex.trim();
  const canInsert = Boolean(element) && source.length > 0 && !preview.error;
  const canTranscribe =
    Boolean(element) &&
    visionModel.length > 0 &&
    !settingsQuery.isLoading &&
    !transcribe.isPending;
  // A note may only credit the model while the source still matches its reply.
  const usesAiSource =
    includeNote && aiProposal !== null && aiProposal.latex === source;

  const cropSrc = element
    ? api.assetUrl(projectId, element.asset_id, element.updated_at)
    : null;

  const handleTranscribe = () => {
    if (!element || !canTranscribe) return;
    transcribe.mutate(element.id);
  };

  const handleInsert = () => {
    if (!element || !canInsert) return;
    const status = element.verified
      ? t("elements.verified")
      : t("elements.unverified");
    let note: string | null = null;
    if (includeNote) {
      note = usesAiSource
        ? t("elements.formula.aiSourceNote", {
            page: pageNumber ?? "—",
            model: aiProposal?.model ?? "",
            status,
          })
        : t("elements.formula.sourceNote", {
            page: pageNumber ?? "—",
            status,
          });
    }
    insertEquation({ latex: source, numbered, note });
    toast.success(t("elements.formula.inserted"));
    onOpenChange(false);
    onInserted?.();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-2xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sigma className="size-icon-sm text-primary" aria-hidden="true" />
            {t("elements.formula.title", { page: pageNumber ?? "—" })}
          </DialogTitle>
          <DialogDescription>{t("elements.formula.description")}</DialogDescription>
        </DialogHeader>

        <div className="scrollbar-thin -mx-1 min-h-0 flex-1 space-y-4 overflow-y-auto px-1">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
            {cropSrc ? (
              <figure className="shrink-0 space-y-1">
                <img
                  src={cropSrc}
                  alt={t("elements.formula.cropAlt")}
                  className="max-h-32 w-auto max-w-44 rounded-md border border-border/70 bg-muted/30 object-contain p-1"
                  draggable={false}
                />
                <figcaption className="text-2xs text-muted-foreground">
                  {t("elements.formula.cropLabel")}
                </figcaption>
              </figure>
            ) : null}

            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label htmlFor="formula-latex">{t("editor.equation.source")}</Label>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={handleTranscribe}
                  disabled={!canTranscribe}
                >
                  {transcribe.isPending ? (
                    <Spinner className="size-icon-sm" />
                  ) : (
                    <Sparkles />
                  )}
                  {t("elements.formula.aiTranscribe")}
                </Button>
              </div>
              <Textarea
                id="formula-latex"
                dir="ltr"
                className="min-h-24 font-mono text-xs"
                value={latex}
                maxLength={4_000}
                spellCheck={false}
                onChange={(event) => setLatex(event.target.value)}
                placeholder="E = mc^2"
              />
              <p className="text-2xs leading-relaxed text-muted-foreground">
                {t("elements.formula.sourceHint")}
              </p>
              {visionModel ? (
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {t("elements.formula.aiHint")}
                </p>
              ) : (
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {t("elements.formula.aiUnavailable")}
                </p>
              )}
              {aiProposal ? (
                <div className="flex flex-wrap items-start gap-1.5 rounded-md border border-warning/30 bg-warning/5 px-2 py-1.5">
                  <Badge variant="warning">
                    <CircleAlert aria-hidden="true" />
                    {t("elements.formula.aiProposed", {
                      model: aiProposal.model,
                    })}
                  </Badge>
                  <p className="text-2xs leading-relaxed text-muted-foreground">
                    {t("elements.formula.aiWarning")}
                  </p>
                </div>
              ) : null}
            </div>
          </div>

          <div className="space-y-1">
            <p className="text-2xs font-medium text-muted-foreground">
              {t("editor.equation.preview")}
            </p>
            <div
              aria-live="polite"
              aria-label={t("editor.equation.preview")}
              className="flex min-h-16 items-center justify-center overflow-x-auto rounded-md border border-border/60 bg-muted/20 px-3 py-2"
            >
              {preview.error ? (
                <p role="alert" className="text-xs leading-relaxed text-destructive">
                  {t("elements.formula.invalid")}
                </p>
              ) : preview.html ? (
                // KaTeX output is generated locally with trust disabled, so the
                // markup contains no links or HTML from the source.
                <div dangerouslySetInnerHTML={{ __html: preview.html }} />
              ) : (
                <p className="text-xs text-muted-foreground">
                  {t("editor.equation.emptyPreview")}
                </p>
              )}
            </div>
          </div>

          <label className="flex items-start gap-2 text-2xs leading-relaxed text-muted-foreground">
            <input
              type="checkbox"
              className="mt-0.5 size-3.5 accent-primary"
              checked={numbered}
              onChange={(event) => setNumbered(event.target.checked)}
            />
            {t("elements.formula.numbered")}
          </label>
        </div>

        <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3 sm:items-center">
          <label className="mr-auto flex items-center gap-1.5 text-2xs text-muted-foreground">
            <input
              type="checkbox"
              className="size-3.5 accent-primary"
              checked={includeNote}
              onChange={(event) => setIncludeNote(event.target.checked)}
            />
            {t("elements.includeNote")}
          </label>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button className="gap-1.5" onClick={handleInsert} disabled={!canInsert}>
            <Sigma />
            {t("elements.formula.insert")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
