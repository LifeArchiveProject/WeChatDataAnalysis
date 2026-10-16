import zipIconUrl from '~/assets/images/wechat/zip.png'
import pdfIconUrl from '~/assets/images/wechat/pdf.png'
import wordIconUrl from '~/assets/images/wechat/word.png'
import excelIconUrl from '~/assets/images/wechat/excel.png'

export const getFileIconKind = (fileName) => {
  if (!fileName) return 'default'
  const ext = String(fileName).split('.').pop()?.toLowerCase() || ''
  switch (ext) {
    case 'pdf':
      return 'pdf'
    case 'zip':
    case 'rar':
    case '7z':
    case 'tar':
    case 'gz':
      return 'zip'
    case 'doc':
    case 'docx':
      return 'doc'
    case 'xls':
    case 'xlsx':
    case 'csv':
      return 'xls'
    case 'ppt':
    case 'pptx':
      return 'ppt'
    case 'txt':
    case 'md':
    case 'log':
      return 'txt'
    default:
      return 'default'
  }
}

export const getFileIconUrl = (fileName) => {
  switch (getFileIconKind(fileName)) {
    case 'pdf':
      return pdfIconUrl
    case 'doc':
      return wordIconUrl
    case 'xls':
      return excelIconUrl
    case 'zip':
      return zipIconUrl
    default:
      return ''
  }
}
