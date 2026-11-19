import { expect, test } from '@playwright/test'

test('starts disarmed and completes the practice replay on the real WebSocket', async ({page}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', {name: 'Studio gesti'})).toBeVisible()
  await expect(page.getByText('Servizio locale')).toBeVisible()
  await expect(page.getByRole('button', {name: 'Abilita controllo desktop'})).toBeDisabled()
  await page.getByRole('button', {name: 'Demo dei gesti'}).click()
  await expect(page.getByText('REPLAY SINTETICO')).toBeVisible()
  await expect(page.getByText('✓ Clic rilevato')).toBeVisible()
  await expect(page.getByText('✓ Rilascio')).toBeVisible()
  await expect.poll(() => page.getByLabel('Distanza di scorrimento').evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  await expect(page.getByText('In pausa · Palmo rilevato')).toBeVisible()
  await expect(page.getByRole('button', {name: 'Abilita controllo desktop'})).toBeDisabled()
  await page.getByRole('button', {name: 'Stop'}).click()
  await expect(page.getByText('Fotocamera spenta').first()).toBeVisible()
})

test('Escape pauses the replay and a fresh source requires new intent', async ({page}) => {
  await page.goto('/')
  await page.getByRole('button', {name: 'Demo dei gesti'}).click()
  await expect(page.getByText('In attesa del pugno')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByText('In pausa · Pausa manuale')).toBeVisible()
  await page.getByRole('button', {name: 'Stop'}).click()
  await page.getByRole('button', {name: 'Calibrazione'}).click()
  await expect(page.getByLabel('Pinza chiusa')).toBeVisible()
})
