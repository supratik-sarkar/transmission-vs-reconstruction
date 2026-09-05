import type { ProviderStatus } from '../lib/contracts';

/**
 * Provider status.
 *
 * Renders presence booleans only. There is no key, no prefix, no suffix and no
 * length anywhere in this component or in the payload that feeds it — a partial
 * fingerprint is unnecessary and is still information about a secret.
 */
export function Providers({ providers }: { providers: ProviderStatus[] }) {
  return (
    <>
      <table>
        <caption className="sr-only">Provider configuration status</caption>
        <thead>
          <tr>
            <th scope="col">Provider</th><th scope="col">State</th>
            <th scope="col">SDK</th><th scope="col">Secret</th><th scope="col">Model pinned</th>
          </tr>
        </thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.provider}>
              <td><code>{p.provider}</code></td>
              <td><span className={`chip chip--${p.state === 'CONFIGURED' ? 'transmitted' : 'unknown'}`}>
                {p.state}</span></td>
              <td>{p.sdk_available ? 'available' : <span className="unavailable">not installed</span>}</td>
              <td>{p.secret_configured ? 'configured' : <span className="unavailable">not configured</span>}</td>
              <td>{p.model_pinned
                ? <code>{p.model}</code>
                : <span className="unavailable">MUST_PIN</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="notice" style={{ marginTop: 16 }}>
        Configuration is reported as a boolean only. No key material — not even a
        length or a suffix — is transmitted to the browser or present in this bundle.
      </p>
    </>
  );
}
