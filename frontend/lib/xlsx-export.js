const encoder = new TextEncoder()

const XML_ENTITIES = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&apos;'
}

const escapeXml = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (char) => XML_ENTITIES[char])

const columnName = (index) => {
  let value = ''
  let current = index
  while (current > 0) {
    const remainder = (current - 1) % 26
    value = String.fromCharCode(65 + remainder) + value
    current = Math.floor((current - 1) / 26)
  }
  return value
}

const crc32Table = (() => {
  const table = new Uint32Array(256)
  for (let index = 0; index < 256; index += 1) {
    let value = index
    for (let bit = 0; bit < 8; bit += 1) value = (value >>> 1) ^ ((value & 1) ? 0xEDB88320 : 0)
    table[index] = value >>> 0
  }
  return table
})()

const crc32 = (bytes) => {
  let value = 0xFFFFFFFF
  for (const byte of bytes) value = (value >>> 8) ^ crc32Table[(value ^ byte) & 0xFF]
  return (value ^ 0xFFFFFFFF) >>> 0
}

const writeUint16 = (view, offset, value) => view.setUint16(offset, value, true)
const writeUint32 = (view, offset, value) => view.setUint32(offset, value >>> 0, true)

const concatBytes = (parts, totalLength) => {
  const result = new Uint8Array(totalLength)
  let offset = 0
  for (const part of parts) {
    result.set(part, offset)
    offset += part.length
  }
  return result
}

const createStoredZip = (entries) => {
  const normalized = entries.map(({ name, content }) => {
    const fileName = encoder.encode(name)
    const data = content instanceof Uint8Array ? content : encoder.encode(content)
    return { fileName, data, checksum: crc32(data) }
  })
  const parts = []
  const centralParts = []
  let localOffset = 0
  let totalLength = 0

  for (const entry of normalized) {
    const header = new Uint8Array(30)
    const view = new DataView(header.buffer)
    writeUint32(view, 0, 0x04034B50)
    writeUint16(view, 4, 20)
    writeUint16(view, 6, 0x0800)
    writeUint16(view, 8, 0)
    writeUint32(view, 14, entry.checksum)
    writeUint32(view, 18, entry.data.length)
    writeUint32(view, 22, entry.data.length)
    writeUint16(view, 26, entry.fileName.length)
    parts.push(header, entry.fileName, entry.data)
    totalLength += header.length + entry.fileName.length + entry.data.length

    const central = new Uint8Array(46)
    const centralView = new DataView(central.buffer)
    writeUint32(centralView, 0, 0x02014B50)
    writeUint16(centralView, 4, 20)
    writeUint16(centralView, 6, 20)
    writeUint16(centralView, 8, 0x0800)
    writeUint16(centralView, 10, 0)
    writeUint32(centralView, 16, entry.checksum)
    writeUint32(centralView, 20, entry.data.length)
    writeUint32(centralView, 24, entry.data.length)
    writeUint16(centralView, 28, entry.fileName.length)
    writeUint32(centralView, 42, localOffset)
    centralParts.push(central, entry.fileName)
    localOffset += header.length + entry.fileName.length + entry.data.length
  }

  const centralLength = centralParts.reduce((sum, part) => sum + part.length, 0)
  const footer = new Uint8Array(22)
  const footerView = new DataView(footer.buffer)
  writeUint32(footerView, 0, 0x06054B50)
  writeUint16(footerView, 8, normalized.length)
  writeUint16(footerView, 10, normalized.length)
  writeUint32(footerView, 12, centralLength)
  writeUint32(footerView, 16, totalLength)
  return concatBytes([...parts, ...centralParts, footer], totalLength + centralLength + footer.length)
}

const cleanSheetName = (value) => {
  const cleaned = String(value || 'Sheet1').replace(/[\[\]:*?/\\]/g, '_').replace(/^'+|'+$/g, '')
  return (cleaned || 'Sheet1').slice(0, 31)
}

const renderSheet = (headers, rows) => {
  const allRows = [headers, ...rows]
  const rowXml = allRows.map((row, rowIndex) => {
    const cells = row.map((value, columnIndex) => {
      const text = String(value == null ? '' : value).replace(/\0/g, '')
      const preserve = /^\s|\s$|\n/.test(text) ? ' xml:space="preserve"' : ''
      const style = rowIndex === 0 ? ' s="1"' : ''
      return `<c r="${columnName(columnIndex + 1)}${rowIndex + 1}" t="inlineStr"${style}><is><t${preserve}>${escapeXml(text)}</t></is></c>`
    }).join('')
    return `<row r="${rowIndex + 1}">${cells}</row>`
  }).join('')
  const rangeEnd = `${columnName(Math.max(1, headers.length))}1`
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rowXml}</sheetData><autoFilter ref="A1:${rangeEnd}"/></worksheet>`
}

export const createXlsxBlob = ({ sheetName, headers, rows }) => {
  const safeName = cleanSheetName(sheetName)
  const sheet = renderSheet(headers, rows)
  const entries = [
    {
      name: '[Content_Types].xml',
      content: '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'
    },
    {
      name: '_rels/.rels',
      content: '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    },
    {
      name: 'xl/workbook.xml',
      content: `<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${escapeXml(safeName)}" sheetId="1" r:id="rId1"/></sheets></workbook>`
    },
    {
      name: 'xl/_rels/workbook.xml.rels',
      content: '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    },
    {
      name: 'xl/styles.xml',
      content: '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf xfId="0"/><xf xfId="0" applyFont="1" fontId="1"/></cellXfs></styleSheet>'
    },
    { name: 'xl/worksheets/sheet1.xml', content: sheet }
  ]
  return new Blob([createStoredZip(entries)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}
