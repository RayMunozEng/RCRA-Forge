using UnrealBuildTool;
public class FurValidationTarget : TargetRules
{
 public FurValidationTarget(TargetInfo Target) : base(Target)
 {
  Type = TargetType.Game; DefaultBuildSettings = BuildSettingsVersion.Latest;
  IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
  ExtraModuleNames.Add("FurValidation");
 }
}
