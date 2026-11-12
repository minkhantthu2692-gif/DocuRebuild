import type { Editor } from "@tiptap/react";
import { Check, Plus, Table2, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Toggle } from "@/components/ui/toggle";
import {
  TABLE_MAX_SIZE,
  TABLE_MIN_SIZE,
  tableInsertOptions,
} from "@/lib/editor-table";

interface EditorTableMenuProps {
  editor: Editor | null;
}

/**
 * Manual table tools. A table is inserted empty and every cell is typed by the
 * user, so this path never invents cells from a source image. When the cursor is
 * inside a table, the same menu exposes row and column edits.
 */
export function EditorTableMenu({ editor }: EditorTableMenuProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");

  const [insertOpen, setInsertOpen] = useState(false);
  const [rows, setRows] = useState(3);
  const [columns, setColumns] = useState(3);
  const [headerRow, setHeaderRow] = useState(true);

  const inTable = Boolean(editor?.isActive("table"));
  const enabled = Boolean(editor?.isEditable);

  const insertTable = () => {
    if (!editor) return;
    editor
      .chain()
      .focus()
      .insertTable(tableInsertOptions(rows, columns, headerRow))
      .run();
    setInsertOpen(false);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant={inTable ? "secondary" : "ghost"}
            size="icon-xs"
            aria-label={t("editor.table.menu")}
            aria-pressed={inTable}
            disabled={!enabled}
          >
            <Table2 />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-w-64">
          <DropdownMenuItem onSelect={() => setInsertOpen(true)}>
            <Table2 />
            <span>{t("editor.table.insert")}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>{t("editor.table.editLabel")}</DropdownMenuLabel>
          <DropdownMenuItem
            disabled={!inTable || !editor?.can().addRowBefore()}
            onSelect={() => editor?.chain().focus().addRowBefore().run()}
          >
            <Plus />
            <span>{t("editor.table.addRowBefore")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!inTable || !editor?.can().addRowAfter()}
            onSelect={() => editor?.chain().focus().addRowAfter().run()}
          >
            <Plus />
            <span>{t("editor.table.addRowAfter")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!inTable || !editor?.can().addColumnBefore()}
            onSelect={() => editor?.chain().focus().addColumnBefore().run()}
          >
            <Plus />
            <span>{t("editor.table.addColumnBefore")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!inTable || !editor?.can().addColumnAfter()}
            onSelect={() => editor?.chain().focus().addColumnAfter().run()}
          >
            <Plus />
            <span>{t("editor.table.addColumnAfter")}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={!inTable || !editor?.can().deleteRow()}
            onSelect={() => editor?.chain().focus().deleteRow().run()}
          >
            <Trash2 />
            <span>{t("editor.table.deleteRow")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!inTable || !editor?.can().deleteColumn()}
            onSelect={() => editor?.chain().focus().deleteColumn().run()}
          >
            <Trash2 />
            <span>{t("editor.table.deleteColumn")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!inTable || !editor?.can().toggleHeaderRow()}
            onSelect={() => editor?.chain().focus().toggleHeaderRow().run()}
          >
            <Check />
            <span>{t("editor.table.toggleHeaderRow")}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            destructive
            disabled={!inTable || !editor?.can().deleteTable()}
            onSelect={() => editor?.chain().focus().deleteTable().run()}
          >
            <Trash2 />
            <span>{t("editor.table.deleteTable")}</span>
          </DropdownMenuItem>
          <DropdownMenuLabel className="max-w-64 whitespace-normal text-2xs font-normal leading-relaxed text-muted-foreground">
            {t("editor.table.note")}
          </DropdownMenuLabel>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={insertOpen} onOpenChange={setInsertOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("editor.table.insertTitle")}</DialogTitle>
            <DialogDescription>{t("editor.table.insertDescription")}</DialogDescription>
          </DialogHeader>
          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              insertTable();
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="editor-table-rows">{t("editor.table.rows")}</Label>
                <Input
                  id="editor-table-rows"
                  type="number"
                  inputMode="numeric"
                  min={TABLE_MIN_SIZE}
                  max={TABLE_MAX_SIZE}
                  value={rows}
                  onChange={(event) => setRows(Number(event.target.value))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="editor-table-columns">{t("editor.table.columns")}</Label>
                <Input
                  id="editor-table-columns"
                  type="number"
                  inputMode="numeric"
                  min={TABLE_MIN_SIZE}
                  max={TABLE_MAX_SIZE}
                  value={columns}
                  onChange={(event) => setColumns(Number(event.target.value))}
                />
              </div>
            </div>

            <Toggle
              pressed={headerRow}
              onPressedChange={setHeaderRow}
              className="gap-2 border border-input px-2.5 py-1.5 text-xs"
            >
              <Check className={headerRow ? "opacity-100" : "opacity-40"} />
              {t("editor.table.headerRow")}
            </Toggle>

            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("editor.table.sizeHint", {
                min: TABLE_MIN_SIZE,
                max: TABLE_MAX_SIZE,
              })}
            </p>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setInsertOpen(false)}>
                {tCommon("actions.cancel")}
              </Button>
              <Button type="submit">{t("editor.table.insertAction")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
