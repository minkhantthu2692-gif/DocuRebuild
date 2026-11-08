import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation("common");
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="glass-panel max-w-md rounded-xl p-8 text-center shadow-sm">
        <p className="font-mono text-3xl font-semibold text-primary">404</p>
        <h1 className="mt-2 text-lg font-semibold tracking-tight">{t("notFound.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("notFound.description")}</p>
        <Button asChild className="mt-5">
          <Link to="/">{t("notFound.action")}</Link>
        </Button>
      </div>
    </div>
  );
}
