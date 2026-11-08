import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api";

/** Maps backend error codes to localized messages. */
export function useApiErrorMessage() {
  const { t, i18n } = useTranslation("errors");

  return (error: unknown): string => {
    if (error instanceof ApiError) {
      if (i18n.exists(error.code, { ns: "errors" })) {
        return t(error.code);
      }
      return error.message || t("generic");
    }
    return t("generic");
  };
}
