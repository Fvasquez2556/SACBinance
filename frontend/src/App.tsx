import { useEffect } from "react";
import Dashboard from "./components/Dashboard";
import { useNotifications } from "./hooks/useNotifications";
import { useWebSocket } from "./hooks/useWebSocket";

export default function App() {
  const { pairs, connected, lastTs } = useWebSocket();
  const { permission, requestPermission, check } = useNotifications();

  useEffect(() => {
    check(pairs);
  }, [pairs, check]);

  return (
    <Dashboard
      pairs={pairs}
      connected={connected}
      lastTs={lastTs}
      notifPermission={permission}
      onRequestNotif={requestPermission}
    />
  );
}
