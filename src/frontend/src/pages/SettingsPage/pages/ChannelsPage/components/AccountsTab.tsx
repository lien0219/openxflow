import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelIdentity,
  useDeleteChannelIdentity,
  useGetChannelIdentitiesPage,
  useRedeemChannelBindingCode,
} from "@/controllers/API/queries/channels";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import useAlertStore from "@/stores/alertStore";

interface AccountsTabProps {
  connectionId: string;
}

export default function AccountsTab({ connectionId }: AccountsTabProps) {
  const { t } = useTranslation();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [bindingCode, setBindingCode] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [deleteTarget, setDeleteTarget] = useState<ChannelIdentity | null>(
    null,
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => {
    setPage(1);
    setDeleteTarget(null);
  }, [connectionId]);

  const { data: result, isLoading } = useGetChannelIdentitiesPage(
    { connectionId, page, pageSize, query },
    { enabled: Boolean(connectionId) },
  );
  const redeemBinding = useRedeemChannelBindingCode();
  const deleteIdentity = useDeleteChannelIdentity();

  const showError = (title: string, error: unknown) =>
    setErrorData({
      title,
      list: [error instanceof Error ? error.message : String(error)],
    });

  const handleRedeemBinding = async () => {
    if (!bindingCode.trim()) return;
    try {
      await redeemBinding.mutateAsync({ code: bindingCode.trim() });
      setBindingCode("");
      setSuccessData({ title: t("channels.toast.accountBound") });
    } catch (error) {
      showError(t("channels.toast.bindingCodeFailed"), error);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteIdentity.mutateAsync({
        connectionId,
        identityId: deleteTarget.id,
      });
      setDeleteTarget(null);
      setSuccessData({ title: t("channels.toast.accountUnbound") });
    } catch (error) {
      showError(t("channels.toast.deleteFailed"), error);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold">{t("channels.binding.title")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("channels.binding.description")}
          </p>
        </div>
        <div className="flex w-full gap-2 sm:w-auto">
          <Input
            value={bindingCode}
            onChange={(event) =>
              setBindingCode(event.target.value.toUpperCase())
            }
            placeholder={t("channels.binding.placeholder")}
            maxLength={12}
            className="sm:w-48"
          />
          <Button
            onClick={handleRedeemBinding}
            loading={redeemBinding.isPending}
            disabled={!bindingCode.trim()}
          >
            {t("channels.actions.bind")}
          </Button>
        </div>
      </div>

      <Input
        value={queryInput}
        onChange={(event) => setQueryInput(event.target.value)}
        placeholder="搜索渠道用户名称或渠道用户 ID"
      />

      {isLoading ? (
        <Loading />
      ) : (result?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {t("channels.binding.empty")}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {(result?.items ?? []).map((identity) => (
            <div
              key={identity.id}
              className="flex items-center justify-between gap-4 rounded-lg bg-muted/50 px-3 py-3"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {identity.display_name || identity.external_user_id}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {t("channels.binding.channelUser", {
                    channelUser: identity.external_user_id,
                    openxflowUser: identity.openxflow_user_id,
                  })}
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                onClick={() => setDeleteTarget(identity)}
              >
                {t("channels.actions.unbind")}
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-sm">
        <div className="text-muted-foreground">
          共 {result?.total ?? 0} 个绑定账号
        </div>
        <div className="flex items-center gap-2">
          <select
            className="primary-input h-9 w-24"
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
          >
            <option value={20}>20 条</option>
            <option value={50}>50 条</option>
            <option value={100}>100 条</option>
          </select>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            上一页
          </Button>
          <span>
            {page} / {Math.max(1, result?.total_pages ?? 0)}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= (result?.total_pages ?? 0)}
            onClick={() => setPage((current) => current + 1)}
          >
            下一页
          </Button>
        </div>
      </div>

      <DeleteConfirmationModal
        open={Boolean(deleteTarget)}
        setOpen={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        description={
          deleteTarget?.display_name || deleteTarget?.external_user_id || ""
        }
        onConfirm={handleDelete}
      />
    </div>
  );
}
