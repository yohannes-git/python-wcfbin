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
#   consume: reads python.tsv (mode, i, hex) produced by this library,
#            decodes each message with WCF, deserializes it and compares it
#            with Gen.Sample(i) member by member ("OK" or the differences).
#
#   powershell -ExecutionPolicy Bypass -File run.ps1 -Mode produce -Count 2 > messages.tsv
param([string]$Mode, [int]$Count = 3)
$ErrorActionPreference = 'Stop'
$src = [System.IO.File]::ReadAllText("$PSScriptRoot\Interop.cs")
Add-Type -TypeDefinition $src -ReferencedAssemblies System.ServiceModel, System.Runtime.Serialization, System.Xml
if ($Mode -eq 'produce') {
    [Console]::Out.Write([TisInterop.Gen]::Produce($Count))
} else {
    $lines = [System.IO.File]::ReadAllText("$PSScriptRoot\python.tsv")
    [Console]::Out.Write([TisInterop.Gen]::Consume($lines))
}
