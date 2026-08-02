[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DirectoryPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolved = (Resolve-Path -LiteralPath $DirectoryPath).Path
$directory = Get-Item -LiteralPath $resolved
if (-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Smoke credential root must be a regular directory.'
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$sid = $identity.User
$acl = Get-Acl -LiteralPath $resolved
$existingAllowRules = @($acl.Access | Where-Object {
    $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow
})
$existingUnexpected = @($existingAllowRules | Where-Object {
    $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -cne $sid.Value
})
$existingFullControl = @($existingAllowRules | Where-Object {
    $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ceq $sid.Value -and
    ($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq
        [Security.AccessControl.FileSystemRights]::FullControl
})
if ($acl.AreAccessRulesProtected -and
    $existingUnexpected.Count -eq 0 -and
    $existingFullControl.Count -gt 0) {
    [ordered]@{
        schemaVersion = 1
        protected = $true
        currentUserOnly = $true
    } | ConvertTo-Json -Compress
    return
}

$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) {
    [void]$acl.RemoveAccessRuleSpecific($rule)
}
$inheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
    [Security.AccessControl.InheritanceFlags]::ObjectInherit
$accessRule = [Security.AccessControl.FileSystemAccessRule]::new(
    $sid,
    [Security.AccessControl.FileSystemRights]::FullControl,
    $inheritance,
    [Security.AccessControl.PropagationFlags]::None,
    [Security.AccessControl.AccessControlType]::Allow
)
$acl.AddAccessRule($accessRule)
Set-Acl -LiteralPath $resolved -AclObject $acl

$verified = Get-Acl -LiteralPath $resolved
$unexpected = @($verified.Access | Where-Object {
    $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
    $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -cne $sid.Value
})
$fullControl = @($verified.Access | Where-Object {
    $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
    $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ceq $sid.Value -and
    ($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq
        [Security.AccessControl.FileSystemRights]::FullControl
})
if (-not $verified.AreAccessRulesProtected -or
    $unexpected.Count -ne 0 -or
    $fullControl.Count -eq 0) {
    throw 'Smoke credential root ACL was not restricted to the current user.'
}

[ordered]@{
    schemaVersion = 1
    protected = $true
    currentUserOnly = $true
} | ConvertTo-Json -Compress
