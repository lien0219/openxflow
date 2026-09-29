import type { UseMutationResult } from "@tanstack/react-query";
import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

interface DeleteMessagesParams {
  ids: string[];
}

export const useDeleteMessages: useMutationFunctionType<
  undefined,
  DeleteMessagesParams,
  void,
  Error
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();

  const deleteMessage = async ({
    ids,
  }: DeleteMessagesParams): Promise<void> => {
    await api.delete(`${getURL("MESSAGES")}`, {
      data: ids,
    });
  };

  const mutation: UseMutationResult<void, Error, DeleteMessagesParams> = mutate(
    ["useDeleteMessages"],
    deleteMessage,
    {
      ...options,
      onSettled: (...args) => {
        // Deletions shift offsets; refresh loaded pages before requesting older rows.
        queryClient.invalidateQueries({
          queryKey: ["useGetMessagesQuery"],
        });
        queryClient.invalidateQueries({
          queryKey: ["useGetSessionsFromFlowQuery"],
        });
        options?.onSettled?.(...args);
      },
    },
  );

  return mutation;
};
