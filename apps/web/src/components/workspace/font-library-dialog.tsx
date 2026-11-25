import { Check, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useDeleteFont, useFonts, useImportFont, useRefreshFonts } from "@/hooks/use-fonts";
import { cssFontFamily, ensureImportedFontsLoaded } from "@/lib/fonts";

export interface FontLibraryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When provided, clicking a family applies it and closes the dialog. */
  onSelectFamily?: (family: string | null) => void;
  selectedFamily?: string | null;
}

/**
 * One font surface for the editor and Settings. Imported fonts are managed
 * here; installed fonts are listed read-only because the operating system owns
 * their files.
 */
export function FontLibraryDialog({
  open,
  onOpenChange,
  onSelectFamily,
  selectedFamily,
}: FontLibraryDialogProps) {
  const { t } = useTranslation("workspace");
  const errorMessage = useApiErrorMessage();
  const fontsQuery = useFonts();
  const refreshFonts = useRefreshFonts();
  const importFont = useImportFont();
  const deleteFont = useDeleteFont();

  const [query, setQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const families = useMemo(() => fontsQuery.data?.families ?? [], [fontsQuery.data]);
  const selecting = Boolean(onSelectFamily);

  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    if (!term) return families;
    return families.filter((family) => family.name.toLocaleLowerCase().includes(term));
  }, [families, query]);

  // Imported fonts must be registered before their own name can preview.
  useEffect(() => {
    if (!open || !fontsQuery.data) return;
    const importedNames = fontsQuery.data.families
      .filter((family) => family.faces.some((face) => face.source === "imported"))
      .map((family) => family.name);
    void ensureImportedFontsLoaded(fontsQuery.data.families, importedNames);
  }, [open, fontsQuery.data]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setPendingDelete(null);
      setImporting(false);
    }
  }, [open]);

  async function handleFiles(files: FileList | null) {
    const list = files ? Array.from(files) : [];
    if (list.length === 0) return;
    setImporting(true);
    let imported = 0;
    const failures: string[] = [];
    for (const file of list) {
      try {
        await importFont.mutateAsync(file);
        imported += 1;
      } catch (error) {
        failures.push(
          t("editor.font.importFailed", { name: file.name, message: errorMessage(error) }),
        );
      }
    }
    setImporting(false);
    if (fileRef.current) fileRef.current.value = "";
    if (imported > 0) {
      toast.success(t("editor.font.importedToast", { count: imported }));
    }
    for (const failure of failures) toast.error(failure);
  }

  async function removeFamily(familyName: string) {
    const family = families.find((entry) => entry.name === familyName);
    if (!family) return;
    const ids = family.faces
      .filter((face) => face.source === "imported" && face.id)
      .map((face) => face.id as string);
    setPendingDelete(null);
    for (const id of ids) {
      try {
        await deleteFont.mutateAsync(id);
      } catch (error) {
        toast.error(errorMessage(error));
        return;
      }
    }
    toast.success(t("editor.font.removedToast", { name: familyName }));
  }

  function chooseFamily(name: string | null) {
    onSelectFamily?.(name);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("editor.font.title")}</DialogTitle>
          <DialogDescription>{t("editor.font.description")}</DialogDescription>
        </DialogHeader>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-52 flex-1">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("editor.font.search")}
              aria-label={t("editor.font.search")}
              className="pl-8"
            />
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".ttf,.otf,.woff,.woff2"
            multiple
            className="sr-only"
            aria-label={t("editor.font.import")}
            onChange={(event) => void handleFiles(event.target.files)}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={importing}
            onClick={() => fileRef.current?.click()}
          >
            {importing ? <Spinner /> : <Upload />}
            {t("editor.font.import")}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("editor.font.refresh")}
            disabled={refreshFonts.isPending}
            onClick={() => refreshFonts.mutate()}
          >
            <RefreshCw className={refreshFonts.isPending ? "animate-spin" : undefined} />
          </Button>
        </div>
        <p className="mt-1.5 text-2xs text-muted-foreground">{t("editor.font.importHint")}</p>

        <div
          className="scrollbar-thin mt-3 max-h-[52vh] overflow-y-auto rounded-lg border border-border/70"
          role={selecting ? "listbox" : undefined}
          aria-label={t("editor.font.title")}
        >
          {fontsQuery.isPending ? (
            <div className="space-y-2 p-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-10 w-full" />
              ))}
            </div>
          ) : fontsQuery.isError ? (
            <div className="flex flex-col items-center gap-2 p-6 text-center">
              <p className="text-sm text-muted-foreground">
                {errorMessage(fontsQuery.error)}
              </p>
              <Button variant="outline" size="sm" onClick={() => refreshFonts.mutate()}>
                {t("editor.font.refresh")}
              </Button>
            </div>
          ) : (
            <>
              {selecting ? (
                <button
                  type="button"
                  role="option"
                  aria-selected={!selectedFamily}
                  onClick={() => chooseFamily(null)}
                  className="flex w-full items-center justify-between gap-3 border-b border-border/60 px-3 py-2.5 text-left text-sm transition-colors hover:bg-accent"
                >
                  <span>{t("editor.font.default")}</span>
                  {!selectedFamily ? <Check className="size-4 text-primary" /> : null}
                </button>
              ) : null}

              {filtered.length === 0 ? (
                <p className="p-6 text-center text-sm text-muted-foreground">
                  {families.length === 0
                    ? t("editor.font.emptyLibrary")
                    : t("editor.font.empty")}
                </p>
              ) : (
                filtered.map((family) => {
                  const importedFaces = family.faces.filter(
                    (face) => face.source === "imported",
                  );
                  const selected = selectedFamily === family.name;
                  const content = (
                    <>
                      <span className="min-w-0 flex-1">
                        <span
                          className="block truncate text-sm"
                          style={{ fontFamily: cssFontFamily(family.name) }}
                        >
                          {family.name}
                        </span>
                        <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-2xs text-muted-foreground">
                          <span>
                            {t("editor.font.faceCount", { count: family.faces.length })}
                          </span>
                          <Badge variant={family.source === "imported" ? "default" : "outline"}>
                            {t(
                              family.source === "system"
                                ? "editor.font.system"
                                : family.source === "mixed"
                                  ? "editor.font.mixed"
                                  : "editor.font.imported",
                            )}
                          </Badge>
                          {!family.available ? (
                            <Badge variant="warning">{t("editor.font.unavailable")}</Badge>
                          ) : null}
                        </span>
                      </span>
                    </>
                  );

                  if (selecting) {
                    return (
                      <div key={family.name} className="border-b border-border/50 last:border-0">
                        <button
                          type="button"
                          role="option"
                          aria-selected={selected}
                          onClick={() => chooseFamily(family.name)}
                          className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-accent"
                        >
                          {content}
                          {selected ? <Check className="size-4 text-primary" /> : null}
                        </button>
                      </div>
                    );
                  }

                  return (
                    <div key={family.name} className="border-b border-border/50 last:border-0">
                      <div className="flex items-center gap-3 px-3 py-2.5">
                        {content}
                        {importedFaces.length > 0 ? (
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label={t("editor.font.remove")}
                            onClick={() =>
                              setPendingDelete(
                                pendingDelete === family.name ? null : family.name,
                              )
                            }
                          >
                            <Trash2 />
                          </Button>
                        ) : null}
                      </div>
                      {pendingDelete === family.name ? (
                        <div className="flex flex-wrap items-center gap-2 bg-destructive/5 px-3 py-2 text-xs">
                          <span className="flex-1">
                            {t("editor.font.removeConfirm", {
                              count: importedFaces.length,
                              name: family.name,
                            })}
                          </span>
                          <Button variant="ghost" size="sm" onClick={() => setPendingDelete(null)}>
                            {t("editor.font.removeCancel")}
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={deleteFont.isPending}
                            onClick={() => void removeFamily(family.name)}
                          >
                            {t("editor.font.removeAction")}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  );
                })
              )}
            </>
          )}
        </div>

        <p className="mt-3 text-2xs text-muted-foreground">{t("editor.font.storageNote")}</p>
      </DialogContent>
    </Dialog>
  );
}
