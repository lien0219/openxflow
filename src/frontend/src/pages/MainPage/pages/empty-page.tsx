import { useTranslation } from "react-i18next";
import { FaGithub } from "react-icons/fa";
import logoDarkPng from "@/assets/logo_dark.png";
import logoLightPng from "@/assets/logo_light.png";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import CardsWrapComponent from "@/components/core/cardsWrapComponent";
import { useStartNewFlow } from "@/components/core/flowBuilderWelcome/hooks/use-start-new-flow";
import { Button } from "@/components/ui/button";
import { DotBackgroundDemo } from "@/components/ui/dot-background";
import { BUG_REPORT_URL, DOCS_URL, GITHUB_URL } from "@/constants/constants";
import useUploadFlow from "@/hooks/flows/use-upload-flow";
import useAlertStore from "@/stores/alertStore";
import useFlowsManagerStore from "@/stores/flowsManagerStore";
import { useUtilityStore } from "@/stores/utilityStore";
import useFileDrop from "../hooks/use-on-file-drop";

export const EmptyPageCommunity = ({
  setOpenModal,
}: {
  setOpenModal: (open: boolean) => void;
}) => {
  const { t } = useTranslation();
  const handleFileDrop = useFileDrop(undefined);
  const startNewFlow = useStartNewFlow();
  const uploadFlow = useUploadFlow();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const examples = useFlowsManagerStore((state) => state.examples);
  const hideStarterProjects = useUtilityStore(
    (state) => state.hideStarterProjects,
  );

  const handleImport = () => {
    uploadFlow({})
      .then(() => {
        setSuccessData({ title: t("success.fileUploaded") });
      })
      .catch((error) => {
        setErrorData({
          title: t("errors.uploadFile"),
          list: [error instanceof Error ? error.message : String(error)],
        });
      });
  };

  return (
    <DotBackgroundDemo>
      <CardsWrapComponent
        dragMessage={t("home.dragFlowsOrComponents")}
        onFileDrop={handleFileDrop}
      >
        <div className="m-0 h-full w-full bg-background p-0">
          <div className="z-50 mx-auto flex h-full w-full max-w-5xl flex-col items-center justify-center gap-7 px-5 py-12 sm:px-8">
            <div className="z-50 flex max-w-2xl flex-col items-center gap-3 text-center">
              <div className="z-50 dark:hidden">
                <img
                  src={logoLightPng}
                  alt={t("common.langflowLogoLight")}
                  data-testid="empty_page_logo_light"
                  className="h-16 w-16 pointer-events-none select-none"
                />
              </div>
              <div className="z-50 hidden dark:block">
                <img
                  src={logoDarkPng}
                  alt={t("common.langflowLogoDark")}
                  data-testid="empty_page_logo_dark"
                  className="h-16 w-16 pointer-events-none select-none"
                />
              </div>
              <h1
                data-testid="mainpage_title"
                className="z-50 font-chivo text-2xl font-semibold text-foreground sm:text-3xl"
              >
                {t("page.homeTitle")}
              </h1>
              <p
                data-testid="empty_page_description"
                className="z-50 text-base leading-7 text-secondary-foreground"
              >
                {t("page.homeDescription")}
              </p>
            </div>

            <div className="z-50 flex w-full max-w-xl flex-col items-center gap-4">
              <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Button
                  variant="default"
                  className="w-full sm:w-auto"
                  onClick={() => startNewFlow()}
                  id="new-project-btn"
                  data-testid="new_project_btn_empty_page"
                >
                  <ForwardedIconComponent
                    name="Plus"
                    aria-hidden="true"
                    className="h-4 w-4"
                  />
                  <span>{t("page.homeCreateFlow")}</span>
                </Button>
                <Button
                  variant="outline"
                  className="w-full sm:w-auto"
                  onClick={handleImport}
                  data-testid="empty_page_import_flow_button"
                >
                  <ForwardedIconComponent
                    name="Upload"
                    aria-hidden="true"
                    className="h-4 w-4"
                  />
                  <span>{t("page.homeImportFlow")}</span>
                </Button>
              </div>
              <p
                data-testid="empty_page_drag_and_drop_text"
                className="cursor-default text-center text-xs text-muted-foreground"
              >
                {t("page.homeDropFlow")}
              </p>
              {!hideStarterProjects && examples.length > 0 && (
                <Button
                  variant="ghost"
                  className="text-muted-foreground"
                  onClick={() => setOpenModal(true)}
                  data-testid="empty_page_templates_button"
                >
                  <ForwardedIconComponent
                    name="LayoutGrid"
                    aria-hidden="true"
                    className="h-4 w-4"
                  />
                  <span>{t("page.homeStartFromTemplate")}</span>
                </Button>
              )}
            </div>
            <div className="z-50 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              <Button
                unstyled
                className="flex items-center gap-1 hover:text-foreground"
                onClick={() =>
                  window.open(GITHUB_URL, "_blank", "noopener,noreferrer")
                }
                data-testid="empty_page_github_button"
              >
                <FaGithub className="h-4 w-4" aria-hidden="true" />
                GitHub
              </Button>
              <span aria-hidden="true">·</span>
              <Button
                unstyled
                className="hover:text-foreground"
                onClick={() =>
                  window.open(DOCS_URL, "_blank", "noopener,noreferrer")
                }
              >
                {t("page.homeDocumentation")}
              </Button>
              <span aria-hidden="true">·</span>
              <Button
                unstyled
                className="hover:text-foreground"
                onClick={() =>
                  window.open(BUG_REPORT_URL, "_blank", "noopener,noreferrer")
                }
              >
                {t("page.homeReportIssue")}
              </Button>
            </div>
          </div>
        </div>
      </CardsWrapComponent>
    </DotBackgroundDemo>
  );
};

export default EmptyPageCommunity;
