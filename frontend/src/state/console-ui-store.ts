import { create } from "zustand";

export type TicketListFilters = {
  page: number;
  pageSize: number;
  businessStatus: string | null;
  processingStatus: string | null;
  primaryRoute: string | null;
  hasDraft: boolean | null;
  awaitingReview: boolean | null;
  query: string;
};

export type TestEmailDraft = {
  senderEmailRaw: string;
  subject: string;
  bodyText: string;
  autoEnqueue: boolean;
  scenarioLabel: string;
};

const defaultTicketListFilters: TicketListFilters = {
  page: 1,
  pageSize: 20,
  businessStatus: null,
  processingStatus: null,
  primaryRoute: null,
  hasDraft: null,
  awaitingReview: null,
  query: "",
};

const defaultTestEmailDraft: TestEmailDraft = {
  senderEmailRaw: '"Test User" <test.user@example.com>',
  subject: "",
  bodyText: "",
  autoEnqueue: true,
  scenarioLabel: "",
};

type ConsoleUiState = {
  ticketListFilters: TicketListFilters;
  selectedTicketId: string | null;
  selectedRunId: string | null;
  traceDrawerOpen: boolean;
  testEmailDraft: TestEmailDraft;
  setTicketListFilters: (patch: Partial<TicketListFilters>) => void;
  resetTicketListFilters: () => void;
  setSelectedTicketId: (ticketId: string | null) => void;
  setSelectedRunId: (runId: string | null) => void;
  setTraceDrawerOpen: (open: boolean) => void;
  updateTestEmailDraft: (patch: Partial<TestEmailDraft>) => void;
  resetTestEmailDraft: () => void;
};

export const useConsoleUiStore = create<ConsoleUiState>((set) => ({
  ticketListFilters: defaultTicketListFilters,
  selectedTicketId: null,
  selectedRunId: null,
  traceDrawerOpen: false,
  testEmailDraft: defaultTestEmailDraft,
  setTicketListFilters: (patch) =>
    set((state) => ({
      ticketListFilters: {
        ...state.ticketListFilters,
        ...patch,
      },
    })),
  resetTicketListFilters: () =>
    set({
      ticketListFilters: defaultTicketListFilters,
    }),
  setSelectedTicketId: (selectedTicketId) => set({ selectedTicketId }),
  setSelectedRunId: (selectedRunId) => set({ selectedRunId }),
  setTraceDrawerOpen: (traceDrawerOpen) => set({ traceDrawerOpen }),
  updateTestEmailDraft: (patch) =>
    set((state) => ({
      testEmailDraft: {
        ...state.testEmailDraft,
        ...patch,
      },
    })),
  resetTestEmailDraft: () =>
    set({
      testEmailDraft: defaultTestEmailDraft,
    }),
}));
