#pragma once
#include "CoreMinimal.h"
#include "Materials/MaterialExpressionCustomOutput.h"
#include "MaterialExpressionFurSurfaceOutput.generated.h"
/** Decoded fur vectors for the fur-only data pass. Requires the legacy material translator. */
UCLASS(CollapseCategories)
class FURAUTHORING_API UMaterialExpressionFurSurfaceOutput : public UMaterialExpressionCustomOutput
{
    GENERATED_BODY()
public:
    UMaterialExpressionFurSurfaceOutput(const FObjectInitializer& ObjectInitializer);
    UPROPERTY(meta=(RequiredInput="true")) FExpressionInput Normal;
    UPROPERTY(meta=(RequiredInput="true")) FExpressionInput Strand;
    virtual int32 GetNumOutputs() const override { return 2; }
    virtual FString GetFunctionName() const override { return TEXT("GetFurSurface"); }
    virtual FString GetDisplayName() const override { return TEXT("Fur Surface Data"); }
#if WITH_EDITOR
    virtual void GetShaderTags(TArray<FName>& Tags) override { Tags.Add(TEXT("RecoveredFurSurface")); }
    virtual int32 Compile(FMaterialCompiler* Compiler,int32 OutputIndex) override;
    virtual void GetCaption(TArray<FString>& OutCaptions) const override;
    virtual FExpressionInput* GetInput(int32 InputIndex) override;
    virtual FName GetInputName(int32 InputIndex) const override;
    virtual EMaterialValueType GetInputValueType(int32) override { return MCT_Float3; }
#endif
};
