# Interoperability with the WCF binary message encoder of .NET Framework
# (the encoding of net.tcp: ADWS, IPAM, SCVMM, SharePoint, BizTalk...).
#
#   produce: Interop.cs serializes Gen.Sample(i) with DataContractSerializer
#            through BinaryMessageEncodingBindingElement, with a session
#            encoder (MC-NBFSE) and without (MC-NBFS), and prints for each
#            message: mode, i, hex of the message, base64 of the XML that
#            .NET reads from it. tests/data/dotnet_wcf_messages.tsv was
#            produced with -Count 2 on .NET Framework 4.8.1 (release 533320),
#            time zone Romance Standard Time.
#   consume: reads python.tsv (mode, i, hex), the encodings of this
#            library made by encode.py, decodes each message with WCF,
#            deserializes it and compares it with the object it was made
#            from, member by member ("OK" or the differences).
#
# On Windows (the output is written as ASCII: a ">" redirection of
# Windows PowerShell 5.1 would write UTF-16):
#   powershell -ExecutionPolicy Bypass -File run.ps1 -Mode produce -Count 2 -Out messages.tsv
# then, with this library:
#   python3 tests/dotnet/encode.py messages.tsv dotnet > python.tsv
# and, on Windows, with python.tsv next to run.ps1:
#   powershell -ExecutionPolicy Bypass -File run.ps1 -Mode consume
param([ValidateSet('produce', 'consume')][string]$Mode = 'produce',
      [int]$Count = 3, [string]$Out = '')
$ErrorActionPreference = 'Stop'
$src = [System.IO.File]::ReadAllText("$PSScriptRoot\Interop.cs")
Add-Type -TypeDefinition $src -ReferencedAssemblies System.ServiceModel, System.Runtime.Serialization, System.Xml
if ($Mode -eq 'produce') {
    $result = [TisInterop.Gen]::Produce($Count)
} else {
    $result = [TisInterop.Gen]::Consume([System.IO.File]::ReadAllText("$PSScriptRoot\python.tsv"))
}
if ($Out) {
    [System.IO.File]::WriteAllText($Out, $result, [System.Text.Encoding]::ASCII)
} else {
    [Console]::Out.Write($result)
}
