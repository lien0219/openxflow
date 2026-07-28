import HeaderMessagesComponent from "./components/headerMessages";
import PaginatedMessagesView from "./PaginatedMessagesView";

export default function MessagesPage() {
  return (
    <div className="flex h-full w-full flex-col justify-between gap-6">
      <HeaderMessagesComponent />
      <div className="flex min-h-0 h-full w-full flex-col justify-between">
        <PaginatedMessagesView />
      </div>
    </div>
  );
}
