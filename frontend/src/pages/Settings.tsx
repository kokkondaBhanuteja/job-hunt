import { ApplicantPanel } from "./ApplicantPanel";
import { ConnectionPanel } from "./ConnectionPanel";
import { ContextPanel } from "./ContextPanel";
import { ProfilesPanel } from "./ProfilesPanel";
import { SearchPrefsPanel } from "./SearchPrefsPanel";
import { WatchlistPanel } from "./WatchlistPanel";

export function Settings() {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
      <ConnectionPanel />
      <ContextPanel />
      <ApplicantPanel />
      <SearchPrefsPanel />
      <ProfilesPanel />
      <WatchlistPanel />
    </div>
  );
}
