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

  const mutation = mutate(["useDeleteMessages"], deleteMessage, {
    ...options,
    onSettled: (data, error, variables, onMutateResult, context) => {
      queryClient.invalidateQueries({
        queryKey: ["useGetSessionsFromFlowQuery"],
      });
      options?.onSettled?.(data, error, variables, onMutateResult, context);
    },
  });

  return mutation;
};
