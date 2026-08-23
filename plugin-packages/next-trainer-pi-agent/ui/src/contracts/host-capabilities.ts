export interface HostContext {
  route: string;
  locale: string;
  colorScheme: "light" | "dark";
  activeTrainingId?: string;
  activeDatasetId?: string;
}

export interface ThemeTokens {
  background: string;
  panel: string;
  text: string;
  mutedText: string;
  border: string;
  accent: string;
  accentText: string;
  danger: string;
  radius: string;
  fontFamily: string;
  monoFontFamily: string;
}

export interface ResourceSelection {
  resourceId: string;
  kind: "dataset" | "training-config" | "curve" | "knowledge";
  label: string;
}

export interface ResourceSummary extends ResourceSelection {
  summary: string;
  revision: string;
}

export interface ConfirmationRequest {
  toolCallId: string;
}

export interface ConfirmationReference {
  ticketId: string;
  state: "pending" | "approved" | "rejected" | "expired";
}

export interface ArtifactReference {
  artifactId: string;
  title: string;
  kind: string;
}

export interface HostCapabilities {
  readonly environment: {
    getContext(): Promise<HostContext>;
    getTheme(): Promise<ThemeTokens>;
  };
  readonly resources: {
    pick(kinds: ResourceSelection["kind"][]): Promise<ResourceSelection | null>;
    getSummary(resourceId: string): Promise<ResourceSummary>;
  };
  readonly confirmations: {
    request(input: ConfirmationRequest): Promise<ConfirmationReference>;
    getResult(ticketId: string): Promise<ConfirmationReference>;
  };
  readonly artifacts: {
    open(reference: ArtifactReference): Promise<void>;
    download(reference: ArtifactReference): Promise<void>;
  };
  readonly navigation: {
    openExternal(url: string): Promise<void>;
    openPluginRoute(route: string): Promise<void>;
  };
}
