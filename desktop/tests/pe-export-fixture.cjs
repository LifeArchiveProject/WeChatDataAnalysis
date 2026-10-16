"use strict";

function buildWindowsPeWithExports(exportNames) {
  if (!Array.isArray(exportNames) || exportNames.length === 0 || exportNames.length > 32) {
    throw new Error("exportNames must contain between 1 and 32 names");
  }
  const names = exportNames.map((name) => String(name));
  if (names.some((name) => !/^[\x21-\x7e]{1,128}$/.test(name))) {
    throw new Error("fixture export names must be bounded printable ASCII");
  }

  const buffer = Buffer.alloc(0xa00);
  const peOffset = 0x80;
  const coffOffset = peOffset + 4;
  const optionalOffset = coffOffset + 20;
  const optionalSize = 0xf0;
  const sectionOffset = optionalOffset + optionalSize;
  const sectionRva = 0x1000;
  const sectionRawOffset = 0x200;
  const toRva = (rawOffset) => sectionRva + rawOffset - sectionRawOffset;

  buffer.writeUInt16LE(0x5a4d, 0);
  buffer.writeUInt32LE(peOffset, 0x3c);
  buffer.writeUInt32LE(0x00004550, peOffset);
  buffer.writeUInt16LE(0x8664, coffOffset);
  buffer.writeUInt16LE(1, coffOffset + 2);
  buffer.writeUInt16LE(optionalSize, coffOffset + 16);
  buffer.writeUInt16LE(0x2022, coffOffset + 18);

  buffer.writeUInt16LE(0x20b, optionalOffset);
  buffer.writeBigUInt64LE(0x180000000n, optionalOffset + 24);
  buffer.writeUInt32LE(0x1000, optionalOffset + 32);
  buffer.writeUInt32LE(0x200, optionalOffset + 36);
  buffer.writeUInt32LE(0x2000, optionalOffset + 56);
  buffer.writeUInt32LE(0x200, optionalOffset + 60);
  buffer.writeUInt32LE(16, optionalOffset + 108);
  buffer.writeUInt32LE(sectionRva, optionalOffset + 112);
  buffer.writeUInt32LE(0x500, optionalOffset + 116);

  buffer.write(".rdata\0\0", sectionOffset, "ascii");
  buffer.writeUInt32LE(0x800, sectionOffset + 8);
  buffer.writeUInt32LE(sectionRva, sectionOffset + 12);
  buffer.writeUInt32LE(0x800, sectionOffset + 16);
  buffer.writeUInt32LE(sectionRawOffset, sectionOffset + 20);
  buffer.writeUInt32LE(0x40000040, sectionOffset + 36);

  const exportDirectoryOffset = sectionRawOffset;
  const functionsOffset = 0x240;
  const namesOffset = 0x2c0;
  const ordinalsOffset = 0x340;
  const dllNameOffset = 0x380;
  let stringOffset = 0x3a0;
  const codeOffset = 0x900;

  buffer.writeUInt32LE(toRva(dllNameOffset), exportDirectoryOffset + 12);
  buffer.writeUInt32LE(1, exportDirectoryOffset + 16);
  buffer.writeUInt32LE(names.length, exportDirectoryOffset + 20);
  buffer.writeUInt32LE(names.length, exportDirectoryOffset + 24);
  buffer.writeUInt32LE(toRva(functionsOffset), exportDirectoryOffset + 28);
  buffer.writeUInt32LE(toRva(namesOffset), exportDirectoryOffset + 32);
  buffer.writeUInt32LE(toRva(ordinalsOffset), exportDirectoryOffset + 36);
  buffer.write("wechatdb_client.dll\0", dllNameOffset, "ascii");

  names.forEach((name, index) => {
    const encoded = Buffer.from(`${name}\0`, "ascii");
    if (stringOffset + encoded.length >= codeOffset) {
      throw new Error("fixture export strings exceed the synthetic PE section");
    }
    buffer.writeUInt32LE(toRva(codeOffset + index), functionsOffset + index * 4);
    buffer.writeUInt32LE(toRva(stringOffset), namesOffset + index * 4);
    buffer.writeUInt16LE(index, ordinalsOffset + index * 2);
    encoded.copy(buffer, stringOffset);
    buffer[codeOffset + index] = 0xc3;
    stringOffset += encoded.length;
  });
  return buffer;
}

module.exports = { buildWindowsPeWithExports };
