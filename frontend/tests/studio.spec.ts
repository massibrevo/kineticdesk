import { expect, test, type WebSocketRoute } from '@playwright/test'

test('starts disarmed and completes the practice replay on the real WebSocket', async ({page}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', {name: 'Gesture Studio'})).toBeVisible()
  await expect(page.getByText('Local service')).toBeVisible()
  await expect(page.getByText('SIMULATION · DRY-RUN')).toBeVisible()
  await page.getByRole('button', {name: 'Gesture demo'}).click()
  await expect(page.getByText('SYNTHETIC REPLAY')).toBeVisible()
  await expect(page.getByText('✓ Click detected')).toBeVisible()
  await expect(page.getByText('✓ Drop detected')).toBeVisible()
  await expect.poll(() => page.getByLabel('Scroll distance').evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  await expect(page.getByText('Paused · Palm detected')).toBeVisible()
  await expect(page.getByText('SIMULATION · DRY-RUN')).toBeVisible()
  await page.getByRole('button', {name: 'Stop'}).click()
  await expect(page.getByText('Camera off').first()).toBeVisible()
})

test('Escape pauses the replay and a fresh source requires new intent', async ({page}) => {
  await page.goto('/')
  await page.getByRole('button', {name: 'Gesture demo'}).click()
  await expect(page.getByText('Waiting for a fist')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByText('Paused · Paused manually')).toBeVisible()
  await page.getByRole('button', {name: 'Stop'}).click()
  await page.getByRole('button', {name: 'Calibration'}).click()
  await expect(page.getByLabel('Closed pinch')).toBeVisible()
})

test('expands and restores the workspace while keeping session controls available', async ({page}) => {
  await page.goto('/')
  await page.getByRole('button', {name: 'Expand Studio'}).click()
  await expect(page.locator('.shell')).toHaveClass(/expanded/)
  await expect(page.getByRole('button', {name: 'Stop'})).toBeVisible()
  await page.getByRole('button', {name: 'Reduce Studio'}).click()
  await expect(page.locator('.shell')).not.toHaveClass(/expanded/)
})


test('switches language across the Studio and retains it on reload', async ({page}) => {
  await page.goto('/')
  await page.getByRole('combobox', {name: 'Language'}).selectOption('it')
  await expect(page.getByRole('heading', {name: 'Studio gesti'})).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'it')
  await page.reload()
  await expect(page.getByRole('heading', {name: 'Studio gesti'})).toBeVisible()
  await page.getByRole('button', {name: 'Calibrazione'}).click()
  await expect(page.getByLabel('Pinza chiusa')).toBeVisible()
  await page.getByRole('combobox', {name: 'Lingua'}).selectOption('en')
  await expect(page.getByRole('heading', {name: 'Control profile'})).toBeVisible()
  await expect(page.getByLabel('Closed pinch')).toBeVisible()
})

test('reconnects after a dropped WebSocket and stays disarmed', async ({page}) => {
  let firstSocket: WebSocketRoute | undefined
  let connections = 0
  await page.routeWebSocket('**/ws', socket => {
    if (++connections === 1) firstSocket = socket
    socket.connectToServer()
  })
  await page.goto('/')
  await page.getByRole('button', {name: 'Gesture demo'}).click()
  await expect(page.getByText('SYNTHETIC REPLAY')).toBeVisible()
  await firstSocket?.close({code: 1011, reason: 'test disconnect'})
  await expect.poll(() => connections).toBeGreaterThan(1)
  await expect(page.getByText('Local service')).toBeVisible()
  await expect(page.getByText('Camera off', {exact: true})).toBeVisible()
  await expect(page.getByRole('button', {name: 'Start scan and control the Mac'})).toBeEnabled()
})
