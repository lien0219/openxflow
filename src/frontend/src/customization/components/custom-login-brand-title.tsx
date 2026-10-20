import { useTranslation } from "react-i18next";

// OSS default product name on the login page. Downstream overlays replace this
// with an edition-specific brand without changing layout.
export default function CustomLoginBrandTitle() {
  const { t } = useTranslation();
  return <>{t("common.productName")}</>;
}
