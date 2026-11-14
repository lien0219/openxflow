import { LangflowCounts } from "@/components/core/appHeaderComponent/components/langflow-counts";
import { ENABLE_SOCIAL_LINKS } from "@/customization/feature-flags";

export function CustomLangflowCounts() {
  return ENABLE_SOCIAL_LINKS ? <LangflowCounts /> : null;
}

export default CustomLangflowCounts;
