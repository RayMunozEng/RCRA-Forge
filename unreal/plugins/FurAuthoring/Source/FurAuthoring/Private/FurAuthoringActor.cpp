#include "FurAuthoringActor.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"

AFurAuthoringActor::AFurAuthoringActor()
{
    PrimaryActorTick.bCanEverTick = false;
    Shells = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("FurShells"));
    SetRootComponent(Shells);
    Shells->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Shells->SetGenerateOverlapEvents(false);
    Shells->SetNumCustomDataFloats(1);
}

void AFurAuthoringActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    RebuildFur();
}

void AFurAuthoringActor::RebuildFur()
{
    Shells->ClearInstances();
    Shells->SetStaticMesh(SourceMesh);
    DynamicMaterial = nullptr;
    if (!FurMaterial)
        FurMaterial = LoadObject<UMaterialInterface>(nullptr,
            TEXT("/FurAuthoring/Materials/M_FurAuthoring.M_FurAuthoring"));
    if (!SourceMesh || !FurMaterial) return;
    DynamicMaterial = UMaterialInstanceDynamic::Create(FurMaterial, this);
    for (int32 Slot = 0; Slot < SourceMesh->GetStaticMaterials().Num(); ++Slot)
        Shells->SetMaterial(Slot, DynamicMaterial);
    const int32 Count = FMath::Clamp(ShellCount, 1, 64);
    for (int32 Layer = 0; Layer < Count; ++Layer)
    {
        const int32 Instance = Shells->AddInstance(FTransform::Identity);
        const float Depth = Count > 1 ? float(Layer) / float(Count - 1) : 0.0f;
        Shells->SetCustomDataValue(Instance, 0, Depth, false);
    }
    UpdateParameters();
    Shells->MarkRenderStateDirty();
}

void AFurAuthoringActor::UpdateParameters()
{
    if (!DynamicMaterial) return;
    DynamicMaterial->SetScalarParameterValue(TEXT("RecoveredShellCount"), float(FMath::Clamp(ShellCount, 1, 64)));
    if (bUseMapControls)
    {
        DynamicMaterial->SetScalarParameterValue(TEXT("RecoveredDensity"), FMath::Clamp(RecoveredDensity, 1.f, 64.f));
        DynamicMaterial->SetScalarParameterValue(TEXT("OffsetScale"), FMath::Clamp(GroomStrength, 0.f, 4.f));
        // Disabled maps use shader defaults. Reset bindings too, so removing a
        // map releases the old texture rather than retaining a stale override.
        UTexture2D* White = LoadObject<UTexture2D>(nullptr, TEXT("/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture"));
        DynamicMaterial->SetTextureParameterValue(TEXT("LengthMap"), LengthMap ? LengthMap.Get() : White);
        DynamicMaterial->SetTextureParameterValue(TEXT("DensityMap"), DensityMap ? DensityMap.Get() : White);
        DynamicMaterial->SetTextureParameterValue(TEXT("GroomMap"), GroomMap ? GroomMap.Get() : White);
    }
    DynamicMaterial->SetScalarParameterValue(TEXT("UseLengthMap"), bUseMapControls && LengthMap ? 1.f : 0.f);
    DynamicMaterial->SetScalarParameterValue(TEXT("UseDensityMap"), bUseMapControls && DensityMap ? 1.f : 0.f);
    DynamicMaterial->SetScalarParameterValue(TEXT("UseGroomMap"), bUseMapControls && GroomMap ? 1.f : 0.f);
    DynamicMaterial->SetScalarParameterValue(TEXT("FurLength"), FMath::Clamp(Length, 0.f, 30.f));
    DynamicMaterial->SetScalarParameterValue(TEXT("Density"), FMath::Clamp(Density, 1.f, 512.f));
    DynamicMaterial->SetScalarParameterValue(TEXT("StrandWidth"), FMath::Clamp(StrandWidth, .02f, .48f));
    DynamicMaterial->SetScalarParameterValue(TEXT("Roughness"), FMath::Clamp(Roughness, .05f, 1.f));
    DynamicMaterial->SetScalarParameterValue(TEXT("Wetness"), FMath::Clamp(Wetness, 0.f, 1.f));
    DynamicMaterial->SetScalarParameterValue(TEXT("WindStrength"), FMath::Clamp(WindStrength, 0.f, 2.f));
    DynamicMaterial->SetScalarParameterValue(TEXT("WindSpeed"), FMath::Clamp(WindSpeed, 0.f, 10.f));
    DynamicMaterial->SetVectorParameterValue(TEXT("RootColor"), RootColor);
    DynamicMaterial->SetVectorParameterValue(TEXT("TipColor"), TipColor);
    DynamicMaterial->SetVectorParameterValue(TEXT("Groom"), FLinearColor(Groom.X, Groom.Y, Groom.Z, 0));
    const FVector Wind = WindDirection.GetSafeNormal();
    DynamicMaterial->SetVectorParameterValue(TEXT("WindDirection"), FLinearColor(Wind.X, Wind.Y, Wind.Z, 0));
    // Expand culling bounds for normal extrusion plus tangential comb/wind bend.
    if (SourceMesh)
    {
        const float Radius = FMath::Max(SourceMesh->GetBounds().SphereRadius, 1.f);
        const float MaxBend = Groom.Size() + 1.35f * FMath::Clamp(WindStrength, 0.f, 2.f);
        Shells->SetBoundsScale(1.f + FMath::Max(Length, 0.f) * (1.f + MaxBend) / Radius);
    }
}

void AFurAuthoringActor::SetWeather(float NewWetness, float NewWindStrength)
{
    Wetness = FMath::Clamp(NewWetness, 0.f, 1.f);
    WindStrength = FMath::Clamp(NewWindStrength, 0.f, 2.f);
    UpdateParameters();
}

void AFurAuthoringActor::ShortFurPreset()
{
    RecoveredDensity = 12.f; GroomStrength = 1.f;
    Length = 1.5f; Density = 140.f; StrandWidth = .18f; ShellCount = 24;
    Groom = FVector(.25, 0, 0); Roughness = .65f;
    RebuildFur();
}

void AFurAuthoringActor::WoolPreset()
{
    RecoveredDensity = 3.f; GroomStrength = 0.f;
    Length = 6.f; Density = 70.f; StrandWidth = .32f; ShellCount = 32;
    Groom = FVector::ZeroVector; Roughness = .85f;
    RootColor = FLinearColor(.35f, .32f, .28f); TipColor = FLinearColor(.8f, .76f, .67f);
    RebuildFur();
}

void AFurAuthoringActor::UseMappedFur()
{
    UMaterialInterface* Mapped = LoadObject<UMaterialInterface>(nullptr,
        TEXT("/FurAuthoring/Materials/M_FurAuthoringMaps.M_FurAuthoringMaps"));
    if (!Mapped) return;
    bUseMapControls = true;
    FurMaterial = Mapped;
    RebuildFur();
}

void AFurAuthoringActor::SetFurMaps(UTexture2D* NewLengthMap, UTexture2D* NewDensityMap, UTexture2D* NewGroomMap)
{
    LengthMap = NewLengthMap; DensityMap = NewDensityMap; GroomMap = NewGroomMap;
    UpdateParameters();
}
