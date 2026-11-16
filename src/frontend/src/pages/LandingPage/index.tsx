import { useRef } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@/components/common/genericIconComponent";
import LanguageSelector from "@/components/core/appHeaderComponent/components/LanguageSelector";
import { CustomLink } from "@/customization/components/custom-link";
import { useDocumentTitle } from "@/hooks/use-document-title";
import CapabilityVisual from "./components/CapabilityVisual";
import LandingHeader from "./components/LandingHeader";
import ParticleWater from "./components/ParticleWater";
import WorkflowPreview from "./components/WorkflowPreview";
import {
  LandingMotionProvider,
  useLandingMotion,
} from "./hooks/use-landing-motion";
import { useLandingScroll } from "./hooks/use-landing-scroll";
import "./landing.css";

const capabilities = [
  {
    title: "landing.visualTitle",
    description: "landing.visualDescription",
    visual: "canvas",
  },
  {
    title: "landing.connectTitle",
    description: "landing.connectDescription",
    visual: "knowledge",
  },
  {
    title: "landing.buildTitle",
    description: "landing.buildDescription",
    visual: "integration",
  },
] as const;

export default function LandingPage() {
  return (
    <LandingMotionProvider>
      <LandingPageContent />
    </LandingMotionProvider>
  );
}

function LandingPageContent() {
  const { t } = useTranslation();
  const { paused, reducedMotion, documentVisible } = useLandingMotion();
  const scrollRef = useRef<HTMLDivElement>(null);
  const { compact, activeSection, selectSection } = useLandingScroll(scrollRef);
  useDocumentTitle(t("landing.pageTitle"));

  return (
    <div
      ref={scrollRef}
      className="landing-page"
      data-testid="landing-page"
      data-motion={
        reducedMotion
          ? "static"
          : paused || !documentVisible
            ? "paused"
            : "running"
      }
    >
      <a href="#main-content" className="landing-skip-link">
        {t("landing.skipToContent")}
      </a>
      <div className="landing-atmosphere" aria-hidden="true">
        <ParticleWater variant="ambient" />
        <div className="landing-orbit landing-orbit-one" />
        <div className="landing-orbit landing-orbit-two" />
        <div className="landing-orbit landing-orbit-three" />
        <div className="landing-grain" />
      </div>
      <LandingHeader
        compact={compact}
        activeSection={activeSection}
        onNavigate={selectSection}
      />
      <main id="main-content" tabIndex={-1} className="landing-main">
        <section aria-labelledby="landing-title" className="landing-hero">
          <ParticleWater />
          <div className="landing-hero-content">
            <p className="landing-eyebrow">
              <span className="landing-live-dot" aria-hidden="true" />
              {t("landing.eyebrow")}
            </p>
            <h1 id="landing-title" data-testid="landing-title">
              <span>{t("landing.heroTitle")}</span>{" "}
              <span className="landing-title-accent">
                {t("landing.heroTitleAccent")}
              </span>
            </h1>
            <p className="landing-hero-description">
              {t("landing.heroDescription")}
            </p>
            <div className="landing-hero-actions">
              <CustomLink
                to="/flows"
                className="landing-button landing-button-primary"
              >
                {t("landing.startBuilding")}
                <Icon name="ArrowUpRight" aria-hidden="true" />
              </CustomLink>
              <a
                href="#workflow"
                className="landing-button landing-button-glass"
              >
                <Icon name="Workflow" aria-hidden="true" />
                {t("landing.exploreWorkflow")}
              </a>
            </div>
          </div>
        </section>
        <section
          id="workflow"
          aria-labelledby="workflow-title"
          className="landing-workflow-section"
          data-reveal
        >
          <WorkflowPreview />
        </section>
        <section
          id="capabilities"
          aria-labelledby="capabilities-title"
          className="landing-capabilities"
        >
          <div className="landing-section-heading" data-reveal>
            <p className="landing-section-label">
              {t("landing.capabilitiesNav")}
            </p>
            <h2 id="capabilities-title">{t("landing.capabilitiesTitle")}</h2>
          </div>
          <div className="landing-capability-grid">
            {capabilities.map((capability, index) => (
              <CapabilityVisual
                key={capability.title}
                variant={capability.visual}
                title={capability.title}
                description={capability.description}
                index={index}
              />
            ))}
          </div>
        </section>
      </main>
      <footer className="landing-footer">
        <p>{t("landing.copyright", { year: new Date().getFullYear() })}</p>
        <div className="landing-language">
          <Icon name="Languages" aria-hidden="true" />
          <LanguageSelector />
        </div>
      </footer>
    </div>
  );
}
