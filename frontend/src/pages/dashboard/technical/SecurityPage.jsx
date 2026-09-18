import { useEffect, useState } from "react";

import Card from "../../../components/Card.jsx";
import PriceReVerificationCard from "../../../components/PriceReVerificationCard.jsx";
import SecurityPosturePanel from "../../../components/SecurityPosturePanel.jsx";
import SecurityTrustBoundaryPanel from "../../../components/SecurityTrustBoundaryPanel.jsx";
import TokenSecurityCard from "../../../components/TokenSecurityCard.jsx";
import useAuth from "../../../hooks/useAuth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function AuthStatusCard() {
  const { loading, isSignedIn, isAdmin, user } = useAuth();
  return (
    <Card title="Authentication &amp; Access Control">
      {loading ? (
        <p className="font-body text-sm text-ink-soft">Checking...</p>
      ) : isSignedIn ? (
        <div className="space-y-1.5 font-body text-sm">
          <div className="flex justify-between"><span className="text-ink-soft">Signed in as</span><span className="font-medium text-ink">{user?.email}</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">Role</span><span className="font-medium text-ink">{user?.role}</span></div>
          <div className="mt-2 space-y-1">
            <p className="text-ink-soft">Protected routes</p>
            <p className="text-moss-dark">✓ Merchant Dashboard {isAdmin ? "(access granted)" : "(would be denied — role mismatch)"}</p>
            <p className="text-moss-dark">✓ Sales Analytics</p>
            <p className="text-moss-dark">✓ Technical Control Center</p>
          </div>
        </div>
      ) : (
        <p className="font-body text-sm text-ink-soft/60">Not signed in.</p>
      )}
      <p className="mt-3 font-body text-[11px] text-ink-soft/50">
        This card is informational only. Server-side JWT verification (backend/app/auth.py's require_user/
        require_merchant_admin) remains the authoritative check on every request — a tampered frontend state here
        cannot grant access; the backend independently re-verifies the token's signature and re-derives the role
        every time.
      </p>
    </Card>
  );
}

export default function SecurityPage() {
  const [securityData, setSecurityData] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/security-posture`)
      .then((res) => res.json())
      .then(setSecurityData)
      .catch(() => {});
  }, []);

  const tamperingAttack = securityData?.attacks.find((a) => a.attack_id === "tampering.direct_discount_injection");
  const replayAttack = securityData?.attacks.find((a) => a.attack_id === "replay.approval_token_delayed_reuse");

  return (
    <div className="space-y-4">
      <SecurityTrustBoundaryPanel />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <TokenSecurityCard attack={replayAttack} />
        <PriceReVerificationCard attack={tamperingAttack} />
      </div>
      <AuthStatusCard />
      <SecurityPosturePanel />
    </div>
  );
}
