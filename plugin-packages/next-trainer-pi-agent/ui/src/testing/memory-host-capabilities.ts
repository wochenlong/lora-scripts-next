import type {
  ArtifactReference,
  ConfirmationReference,
  ConfirmationRequest,
  HostCapabilities,
  HostContext,
  ResourceSelection,
  ResourceSummary,
  ThemeTokens,
} from "../contracts/host-capabilities.ts";
import { DEFAULT_LIGHT_THEME } from "../theme/ThemeProvider.tsx";

export class MemoryHostCapabilities implements HostCapabilities {
  readonly openedExternal: string[] = [];
  readonly openedArtifacts: ArtifactReference[] = [];
  readonly downloadedArtifacts: ArtifactReference[] = [];
  readonly copiedText: string[] = [];
  readonly pluginRoutes: string[] = [];
  readonly confirmationRequests: ConfirmationRequest[] = [];
  selectedResource: ResourceSelection | null = null;
  context: HostContext = { route: "/", locale: "zh-CN", colorScheme: "light" };
  theme: ThemeTokens = DEFAULT_LIGHT_THEME;

  readonly environment = {
    getContext: async (): Promise<HostContext> => ({ ...this.context }),
    getTheme: async (): Promise<ThemeTokens> => ({ ...this.theme }),
  };

  readonly resources = {
    pick: async (_kinds: ResourceSelection["kind"][]): Promise<ResourceSelection | null> => (
      this.selectedResource ? { ...this.selectedResource } : null
    ),
    getSummary: async (resourceId: string): Promise<ResourceSummary> => {
      if (!this.selectedResource || this.selectedResource.resourceId !== resourceId) {
        throw new Error(`Unknown resource: ${resourceId}`);
      }
      return { ...this.selectedResource, summary: "Memory resource", revision: "1" };
    },
  };

  readonly confirmations = {
    request: async (input: ConfirmationRequest): Promise<ConfirmationReference> => {
      this.confirmationRequests.push(structuredClone(input));
      return { ticketId: `ticket-${this.confirmationRequests.length}`, state: "pending" };
    },
    getResult: async (ticketId: string): Promise<ConfirmationReference> => ({ ticketId, state: "approved" }),
  };

  readonly artifacts = {
    open: async (reference: ArtifactReference): Promise<void> => {
      this.openedArtifacts.push({ ...reference });
    },
    download: async (reference: ArtifactReference): Promise<void> => {
      this.downloadedArtifacts.push({ ...reference });
    },
  };

  readonly navigation = {
    openExternal: async (url: string): Promise<void> => {
      this.openedExternal.push(url);
    },
    openPluginRoute: async (route: string): Promise<void> => {
      this.pluginRoutes.push(route);
    },
  };

  readonly clipboard = {
    copyText: async (text: string): Promise<void> => {
      this.copiedText.push(text);
    },
  };
}
