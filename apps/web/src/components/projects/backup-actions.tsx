import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";

import { DropdownMenuItem } from "@/components/ui/dropdown-menu";

interface DownloadBackupMenuItemProps {
  onOpen: () => void;
}

/**
 * Opens the backup download dialog. It is a menu item so the same action can live
 * on the dashboard card and in the workspace header, while the dialog itself is
 * owned by the page so it survives the dropdown closing.
 */
export function DownloadBackupMenuItem({ onOpen }: DownloadBackupMenuItemProps) {
  const { t } = useTranslation("dashboard");

  return (
    <DropdownMenuItem onSelect={onOpen}>
      <Download />
      <span>{t("backup.download")}</span>
    </DropdownMenuItem>
  );
}
