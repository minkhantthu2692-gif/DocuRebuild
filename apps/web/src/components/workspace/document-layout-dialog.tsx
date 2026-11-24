import { CircleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CenteredSpinner, Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useDocumentLayout, useSaveDocumentLayout } from "@/hooks/use-document";

interface DocumentLayoutDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Per-project page header and footer for paginated exports.
 *
 * The values are stored with the project and only affect Word and PDF output;
 * Markdown and plain text are not paginated. Saving never touches the document
 * text or its versions.
 */
export function DocumentLayoutDialog({
  projectId,
  open,
  onOpenChange,
}: DocumentLayoutDialogProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const errorMessage = useApiErrorMessage();
  const layoutQuery = useDocumentLayout(projectId, open);
  const saveLayout = useSaveDocumentLayout(projectId);
  const [headerText, setHeaderText] = useState("");
  const [footerText, setFooterText] = useState("");
  const [showPageNumbers, setShowPageNumbers] = useState(true);

  useEffect(() => {
    if (!open || !layoutQuery.data) return;
    setHeaderText(layoutQuery.data.header_text);
    setFooterText(layoutQuery.data.footer_text);
    setShowPageNumbers(layoutQuery.data.show_page_numbers);
  }, [layoutQuery.data, open]);

  const submit = () => {
    saveLayout.mutate(
      {
        header_text: headerText,
        footer_text: footerText,
        show_page_numbers: showPageNumbers,
      },
      {
        onSuccess: () => {
          toast.success(t("editor.pageLayout.saved"));
          onOpenChange(false);
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const busy = layoutQuery.isPending || saveLayout.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("editor.pageLayout.title")}</DialogTitle>
            <DialogDescription>{t("editor.pageLayout.description")}</DialogDescription>
          </DialogHeader>

          {layoutQuery.isError ? (
            <div className="mt-4 flex flex-col items-start gap-3" role="alert">
              <div className="flex items-start gap-2 text-sm text-destructive">
                <CircleAlert className="mt-0.5 size-icon-sm shrink-0" />
                <p>{t("editor.pageLayout.loadError")}</p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void layoutQuery.refetch()}
              >
                {tCommon("actions.retry")}
              </Button>
            </div>
          ) : layoutQuery.isPending ? (
            <CenteredSpinner label={tCommon("loading")} />
          ) : (
            <div className="mt-4 space-y-4">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="page-layout-header">
                    {t("editor.pageLayout.header")}
                  </Label>
                  <span className="text-2xs tabular-nums text-muted-foreground">
                    {headerText.length} / 200
                  </span>
                </div>
                <Input
                  id="page-layout-header"
                  value={headerText}
                  maxLength={200}
                  autoFocus
                  dir="auto"
                  placeholder={t("editor.pageLayout.headerPlaceholder")}
                  onChange={(event) => setHeaderText(event.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="page-layout-footer">
                    {t("editor.pageLayout.footer")}
                  </Label>
                  <span className="text-2xs tabular-nums text-muted-foreground">
                    {footerText.length} / 200
                  </span>
                </div>
                <Input
                  id="page-layout-footer"
                  value={footerText}
                  maxLength={200}
                  dir="auto"
                  placeholder={t("editor.pageLayout.footerPlaceholder")}
                  onChange={(event) => setFooterText(event.target.value)}
                />
              </div>

              <label className="flex items-start justify-between gap-3 text-2xs leading-relaxed text-muted-foreground">
                <span>
                  <span className="block text-xs text-foreground">
                    {t("editor.pageLayout.showPageNumbers")}
                  </span>
                  {t("editor.pageLayout.showPageNumbersHint")}
                </span>
                <Switch
                  className="mt-0.5"
                  checked={showPageNumbers}
                  onChange={(event) => setShowPageNumbers(event.target.checked)}
                />
              </label>

              <div className="rounded-md border border-border/60 bg-muted/20 p-2.5">
                <p className="text-2xs font-medium text-muted-foreground">
                  {t("editor.pageLayout.tokens")}
                </p>
                <p className="mt-0.5 text-2xs leading-relaxed text-muted-foreground">
                  {t("editor.pageLayout.tokensHint")}
                </p>
              </div>

              <p className="text-2xs leading-relaxed text-muted-foreground">
                {t("editor.pageLayout.note")}
              </p>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {tCommon("actions.cancel")}
            </Button>
            <Button type="submit" disabled={busy || layoutQuery.isError}>
              {saveLayout.isPending ? <Spinner /> : null}
              {t("editor.pageLayout.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
