import { afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import * as Sentry from '@sentry/react';
import { monitoringOptions } from '../src/lib/monitoring-options.ts';

const dsn = 'https://0123456789abcdef0123456789abcdef@o1.ingest.de.sentry.io/123';
const privateData = 'PRIVATE-CONTENT-123 patient transcript prompt token /Users/Private/file.txt';
afterEach(async () => { await Sentry.close(100); });

test('disabled, absent and malformed configuration never starts monitoring', () => {
  for (const config of [{ enabled: 'false', dsn }, { dsn }, { enabled: 'true', dsn: '' }, { enabled: 'true', dsn: 'invalid' }]) {
    assert.equal(monitoringOptions('teacherhelper-web', config), undefined);
  }
});

test('real SDK envelope excludes private fields and attachments and sends a terminal error once', async () => {
  const envelopes = [];
  const options = monitoringOptions('teacherhelper-web', { enabled: 'true', dsn, environment: 'test' });
  Sentry.init({ ...options, transport: () => ({
    send: (envelope) => { envelopes.push(envelope); return Promise.resolve({ statusCode: 200 }); },
    flush: () => Promise.resolve(true),
  }) });
  Sentry.setUser({ email: privateData });
  Sentry.setExtra('private', privateData);
  Sentry.setContext('private', { nested: { content: privateData } });
  Sentry.addBreadcrumb({ message: privateData });
  Sentry.getCurrentScope().addAttachment({ filename: 'private.txt', data: privateData });
  const error = new TypeError(privateData);
  Sentry.captureException(error);
  Sentry.captureException(error);
  Sentry.captureMessage(privateData);
  await Sentry.flush(100);
  assert.equal(envelopes.length, 1);
  assert.deepEqual(envelopes[0][1].map(([header]) => header.type), ['event']);
  assert.equal(JSON.stringify(envelopes).includes(privateData), false);
  const event = envelopes[0][1][0][1];
  assert.deepEqual(event.tags, { component: 'teacherhelper-web' });
  for (const field of ['request', 'user', 'contexts', 'extra', 'breadcrumbs', 'transaction']) assert.equal(field in event, false);
});

test('private stack fields are dropped while technical Debug IDs retain source-map association', () => {
  const options = monitoringOptions('teacherhelper-web', { enabled: 'true', dsn });
  const event = options.beforeSend({
    type: undefined,
    exception: { values: [{ type: 'Error', value: privateData, stacktrace: { frames: [
      { filename: 'https://private.example/assets/main-123.js?token=' + privateData, lineno: 5, colno: 2, vars: { privateData } },
      { filename: '/Users/Private/file.txt', function: privateData },
    ] } }] },
    debug_meta: { images: [{ type: 'sourcemap', code_file: 'https://private.example/assets/main-123.js', debug_id: '12345678-1234-1234-1234-123456789abc' }] },
  }, { originalException: new Error(privateData) });
  assert.equal(JSON.stringify(event).includes(privateData), false);
  assert.equal(JSON.stringify(event).includes('private.example'), false);
  assert.deepEqual(event.debug_meta.images, [{ type: 'sourcemap', code_file: '/assets/main-123.js', debug_id: '12345678-1234-1234-1234-123456789abc' }]);
});

test('transport outage does not make capture throw into the application', async () => {
  const options = monitoringOptions('teacherhelper-web', { enabled: 'true', dsn });
  Sentry.init({ ...options, transport: () => ({ send: () => Promise.reject(new Error('offline')), flush: () => Promise.resolve(false) }) });
  assert.doesNotThrow(() => Sentry.captureException(new Error(privateData)));
  assert.equal(await Sentry.flush(100), false);
});

test('cancelled work is not reported as an application failure', async () => {
  const envelopes = [];
  Sentry.init({ ...monitoringOptions('teacherhelper-web', { enabled: 'true', dsn }), transport: () => ({
    send: (envelope) => { envelopes.push(envelope); return Promise.resolve({ statusCode: 200 }); },
    flush: () => Promise.resolve(true),
  }) });
  Sentry.captureException(new DOMException(privateData, 'AbortError'));
  await Sentry.flush(100);
  assert.deepEqual(envelopes, []);
});
