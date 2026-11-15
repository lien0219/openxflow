import type { Frame, Page, Request } from "@playwright/test";
import type { PendingRequestTracker } from "./server-error-contract.mjs";

/** Retire requests abandoned when Chromium replaces their owning document. */
export async function installDocumentRequestCleanup(
  page: Page,
  trackers: PendingRequestTracker<Request>[],
): Promise<() => void> {
  const navigationCandidates = new Map<Frame, Set<Request>>();
  const replacementCandidates = new Map<Frame, Set<Request>>();
  const frameForRequest = (request: Request): Frame | undefined => {
    try {
      return request.frame();
    } catch {
      // Early navigation requests can arrive before their frame exists.
      return undefined;
    }
  };
  const onRequest = (request: Request) => {
    const frame = frameForRequest(request);
    if (!frame) return;
    if (!request.isNavigationRequest()) {
      // An interval or an already-queued XHR can start in the old document
      // after the navigation request. Keep observing until replacement, too.
      if (
        request.resourceType() === "xhr" ||
        request.resourceType() === "fetch"
      ) {
        navigationCandidates.get(frame)?.add(request);
      }
      return;
    }
    navigationCandidates.set(
      frame,
      new Set(
        trackers.flatMap((tracker) =>
          tracker
            .snapshot()
            .filter(
              (pending) =>
                (pending.resourceType() === "xhr" ||
                  pending.resourceType() === "fetch") &&
                frameForRequest(pending) === frame,
            ),
        ),
      ),
    );
  };

  const onFrameDetached = (frame: Frame) => {
    navigationCandidates.delete(frame);
    replacementCandidates.delete(frame);
    for (const tracker of trackers) {
      for (const request of tracker.snapshot()) {
        if (
          !request.isNavigationRequest() &&
          frameForRequest(request) === frame
        ) {
          tracker.finish(request);
        }
      }
    }
  };
  const onFrameNavigated = (frame: Frame) => {
    const candidates = navigationCandidates.get(frame);
    if (!candidates) return;
    // Commit precedes the new document's requests. Freeze the old document's
    // set here, rather than when its asynchronous binding reaches Node.
    replacementCandidates.set(frame, candidates);
    navigationCandidates.delete(frame);
  };

  await page.exposeBinding(
    "__langflowPlaywrightDocumentStarted",
    ({ frame }) => {
      const abandoned = replacementCandidates.get(frame);
      replacementCandidates.delete(frame);
      for (const request of abandoned ?? []) {
        for (const tracker of trackers) tracker.finish(request);
      }
    },
  );
  await page.addInitScript(() => {
    // Init scripts confirm a replacement document, not history/hash changes
    // or aborted navigations. The commit already froze the abandoned set.
    void (
      globalThis as typeof globalThis & {
        __langflowPlaywrightDocumentStarted: () => Promise<void>;
      }
    ).__langflowPlaywrightDocumentStarted();
  });
  page.on("request", onRequest);
  page.on("framedetached", onFrameDetached);
  page.on("framenavigated", onFrameNavigated);

  return () => {
    page.off("request", onRequest);
    page.off("framedetached", onFrameDetached);
    page.off("framenavigated", onFrameNavigated);
    navigationCandidates.clear();
    replacementCandidates.clear();
  };
}
