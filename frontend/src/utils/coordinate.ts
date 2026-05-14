export function displayToImageCoord(
  x: number,
  y: number,
  displayWidth: number,
  displayHeight: number,
  imageWidth: number,
  imageHeight: number
): { x: number; y: number } {
  return {
    x: Math.max(0, Math.min(imageWidth, (x / displayWidth) * imageWidth)),
    y: Math.max(0, Math.min(imageHeight, (y / displayHeight) * imageHeight))
  };
}

export function imageToDisplayCoord(
  x: number,
  y: number,
  displayWidth: number,
  displayHeight: number,
  imageWidth: number,
  imageHeight: number
): { x: number; y: number } {
  return { x: (x / imageWidth) * displayWidth, y: (y / imageHeight) * displayHeight };
}

export function displayBoxToImageBox(
  box: [number, number, number, number],
  displayWidth: number,
  displayHeight: number,
  imageWidth: number,
  imageHeight: number
): [number, number, number, number] {
  const a = displayToImageCoord(box[0], box[1], displayWidth, displayHeight, imageWidth, imageHeight);
  const b = displayToImageCoord(box[2], box[3], displayWidth, displayHeight, imageWidth, imageHeight);
  return [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)];
}

export function imageBoxToDisplayBox(
  box: [number, number, number, number],
  displayWidth: number,
  displayHeight: number,
  imageWidth: number,
  imageHeight: number
): [number, number, number, number] {
  const a = imageToDisplayCoord(box[0], box[1], displayWidth, displayHeight, imageWidth, imageHeight);
  const b = imageToDisplayCoord(box[2], box[3], displayWidth, displayHeight, imageWidth, imageHeight);
  return [a.x, a.y, b.x, b.y];
}
