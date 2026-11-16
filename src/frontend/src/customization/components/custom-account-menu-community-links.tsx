import { AccountMenuCommunityLinks } from "@/components/core/appHeaderComponent/components/AccountMenu/community-links";
import { ENABLE_SOCIAL_LINKS } from "@/customization/feature-flags";

export function CustomAccountMenuCommunityLinks() {
  return ENABLE_SOCIAL_LINKS ? <AccountMenuCommunityLinks /> : null;
}

export default CustomAccountMenuCommunityLinks;
