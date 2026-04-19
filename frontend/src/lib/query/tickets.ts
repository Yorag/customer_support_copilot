import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { controlPlaneApi } from "@/lib/api/controlPlane";
import type {
  ApproveTicketRequest,
  CloseTicketRequest,
  EditAndApproveTicketRequest,
  EscalateTicketRequest,
  GenerateDraftRequest,
  SaveDraftRequest,
  RewriteTicketRequest,
  TicketListQuery,
} from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";

export function useTicketsList(query: TicketListQuery) {
  return useQuery({
    queryKey: queryKeys.tickets(query),
    queryFn: () => controlPlaneApi.listTickets(query),
    placeholderData: keepPreviousData,
  });
}

export function useTicketSnapshot(ticketId: string) {
  return useQuery({
    queryKey: queryKeys.ticketSnapshot(ticketId),
    queryFn: () => controlPlaneApi.getTicketSnapshot(ticketId),
    enabled: ticketId.length > 0,
  });
}

export function useTicketRuns(ticketId: string, page = 1, pageSize = 20) {
  return useQuery({
    queryKey: queryKeys.ticketRuns(ticketId, page, pageSize),
    queryFn: () => controlPlaneApi.getTicketRuns(ticketId, page, pageSize),
    enabled: ticketId.length > 0,
    placeholderData: keepPreviousData,
  });
}

export function useTicketDrafts(ticketId: string) {
  return useQuery({
    queryKey: queryKeys.ticketDrafts(ticketId),
    queryFn: () => controlPlaneApi.getTicketDrafts(ticketId),
    enabled: ticketId.length > 0,
  });
}

function useInvalidateTicketDetail(ticketId: string) {
  const queryClient = useQueryClient();

  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.ticketSnapshot(ticketId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.ticketRuns(ticketId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.ticketDrafts(ticketId) }),
      queryClient.invalidateQueries({ queryKey: ["tickets"] }),
    ]);
  };
}

export function useApproveTicket(ticketId: string) {
  const invalidate = useInvalidateTicketDetail(ticketId);

  return useMutation({
    mutationFn: ({ actorId, payload }: { actorId: string; payload: ApproveTicketRequest }) =>
      controlPlaneApi.approveTicket(ticketId, actorId, payload),
    onSuccess: invalidate,
  });
}

export function useGenerateTicketDraft(ticketId: string) {
  const invalidate = useInvalidateTicketDetail(ticketId);

  return useMutation({
    mutationFn: ({
      actorId,
      payload,
    }: {
      actorId: string;
      payload: GenerateDraftRequest;
    }) => controlPlaneApi.generateTicketDraft(ticketId, actorId, payload),
    onSuccess: invalidate,
  });
}

export function useSaveTicketDraft(ticketId: string) {
  const invalidate = useInvalidateTicketDetail(ticketId);

  return useMutation({
    mutationFn: ({ actorId, payload }: { actorId: string; payload: SaveDraftRequest }) =>
      controlPlaneApi.saveTicketDraft(ticketId, actorId, payload),
    onSuccess: invalidate,
  });
}

export function useEditAndApproveTicket(ticketId: string) {
  const invalidate = useInvalidateTicketDetail(ticketId);

  return useMutation({
    mutationFn: ({
      actorId,
      payload,
    }: {
      actorId: string;
      payload: EditAndApproveTicketRequest;
    }) => controlPlaneApi.editAndApproveTicket(ticketId, actorId, payload),
    onSuccess: invalidate,
  });
}

export function useRewriteTicket(ticketId: string) {
  const invalidate = useInvalidateTicketDetail(ticketId);

  return useMutation({
    mutationFn: ({ actorId, payload }: { actorId: string; payload: RewriteTicketRequest }) =>
      controlPlaneApi.rewriteTicket(ticketId, actorId, payload),
    onSuccess: invalidate,
  });
}

export function useEscalateTicket(ticketId: string) {
  const invalidate = useInvalidateTicketDetail(ticketId);

  return useMutation({
    mutationFn: ({ actorId, payload }: { actorId: string; payload: EscalateTicketRequest }) =>
      controlPlaneApi.escalateTicket(ticketId, actorId, payload),
    onSuccess: invalidate,
  });
}

export function useCloseTicket(ticketId: string) {
  const invalidate = useInvalidateTicketDetail(ticketId);

  return useMutation({
    mutationFn: ({ actorId, payload }: { actorId: string; payload: CloseTicketRequest }) =>
      controlPlaneApi.closeTicket(ticketId, actorId, payload),
    onSuccess: invalidate,
  });
}
