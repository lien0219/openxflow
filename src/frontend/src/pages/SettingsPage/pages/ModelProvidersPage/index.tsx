import { useTranslation } from "react-i18next";
import ModelProvidersContent from "@/modals/modelProviderModal/components/ModelProvidersContent";
import SettingsPageHeader from "@/pages/SettingsPage/components/SettingsPageHeader";

export default function ModelProvidersPage() {
  const { t } = useTranslation();
  return (
    <div className="flex w-full flex-col gap-6">
      <SettingsPageHeader
        title={t("modelProviders.pageTitle")}
        description={t("modelProviders.pageDescription")}
      />
      <div className="flex h-[calc(100dvh-305px)] min-h-60 w-full overflow-hidden rounded-lg border">
        <ModelProvidersContent modelType="all" />
      </div>
    </div>
  );
}
