import {useEffect, useRef, useState} from 'react';
import {NavigateFunction, useSearchParams} from 'react-router-dom';
import {toast} from 'sonner';
import {api, errorMessage} from '../../api/client';
import {DigiLockerGrant} from '../../api/contracts';
const STATE_KEY = 'sampark.digilocker.state';
// Requester side of the simulated OAuth 2.0 authorization-code flow: remember the anti-forgery state, send the citizen to the locker, exchange the code on return.
export const startDigiLocker = (navigate: NavigateFunction, scope: string[], redirect: string) => {
  const state = crypto.randomUUID().replaceAll('-', '');
  sessionStorage.setItem(STATE_KEY, state);
  navigate(`/digilocker/authorize?client_id=sampark&scope=${encodeURIComponent(scope.join(','))}&state=${state}&redirect=${encodeURIComponent(redirect)}`);
};
export const useDigiLockerReturn = (onGrant: (grant: DigiLockerGrant & {application?: any}) => void, applicationId?: string) => {
  const [params, setParams] = useSearchParams(); const handled = useRef(false); const [busy, setBusy] = useState(false);
  useEffect(() => {
    const code = params.get('code'), state = params.get('state'), error = params.get('error');
    if (handled.current || (!code && !error)) return; handled.current = true;
    const clear = () => {const next = new URLSearchParams(params); ['code', 'state', 'error'].forEach(k => next.delete(k)); setParams(next, {replace: true});};
    if (error) {toast.info('You did not share documents from DigiLocker. Nothing was received.'); clear(); return;}
    if (state !== sessionStorage.getItem(STATE_KEY)) {toast.error('The DigiLocker response did not match this request. Please try again.'); clear(); return;}
    setBusy(true);
    api.post('/digilocker/callback', {code, state, ...(applicationId ? {application_id: applicationId} : {})})
      .then(r => {sessionStorage.removeItem(STATE_KEY); onGrant(r.data);})
      .catch(e => toast.error(errorMessage(e)))
      .finally(() => {setBusy(false); clear();});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return busy;
};
