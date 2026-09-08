#include "FurLightingController.h"
#include "FurAuthoringActor.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/DirectionalLight.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/TextureCube.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Math/OrthoMatrix.h"

AFurLightingController::AFurLightingController()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PostUpdateWork;
    ShadowCapture = CreateDefaultSubobject<USceneCaptureComponent2D>(TEXT("FurShadowCapture"));
    SetRootComponent(ShadowCapture);
    ShadowCapture->ProjectionType = ECameraProjectionMode::Orthographic;
    ShadowCapture->CaptureSource = ESceneCaptureSource::SCS_SceneDepth;
    ShadowCapture->PrimitiveRenderMode = ESceneCapturePrimitiveRenderMode::PRM_UseShowOnlyList;
    ShadowCapture->bCaptureEveryFrame = false;
    ShadowCapture->bCaptureOnMovement = false;
    ShadowCapture->bAutoCalculateOrthoPlanes = false;
    ShadowCapture->bUpdateOrthoPlanes = false;
}

void AFurLightingController::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    LastSceneHash = 0;
    bShadowValid = false;
    BindLighting();
}

void AFurLightingController::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    SecondsSinceShadowUpdate += FMath::Max(DeltaSeconds, 0.f);
    uint32 Hash = GetTypeHash(KeyLight.Get());
    if (IsValid(KeyLight)) Hash = HashCombine(Hash, GetTypeHash(KeyLight->GetActorRotation().Quaternion()));
    Hash = HashCombine(Hash, GetTypeHash(bEnableShadows));
    Hash = HashCombine(Hash, GetTypeHash(ShadowWidth));
    for (AActor* Caster : ShadowCasters)
    {
        Hash = HashCombine(Hash, GetTypeHash(Caster));
        if (IsValid(Caster))
        {
            Hash = HashCombine(Hash, GetTypeHash(Caster->GetActorLocation()));
            Hash = HashCombine(Hash, GetTypeHash(Caster->GetActorRotation().Quaternion()));
            Hash = HashCombine(Hash, GetTypeHash(Caster->GetActorScale3D()));
            Hash = HashCombine(Hash, GetTypeHash(Caster->IsHidden()));
            TInlineComponentArray<UPrimitiveComponent*> Components(Caster);
            for (UPrimitiveComponent* Component : Components)
            {
                Hash = HashCombine(Hash, GetTypeHash(Component));
                Hash = HashCombine(Hash, GetTypeHash(Component->GetComponentLocation()));
                Hash = HashCombine(Hash, GetTypeHash(Component->GetComponentRotation().Quaternion()));
                Hash = HashCombine(Hash, GetTypeHash(Component->GetComponentScale()));
                Hash = HashCombine(Hash, GetTypeHash(Component->IsVisible()));
            }
        }
    }
    for (AFurAuthoringActor* Target : Targets)
    {
        Hash = HashCombine(Hash, GetTypeHash(Target));
        if (IsValid(Target))
        {
            Hash = HashCombine(Hash, GetTypeHash(Target->GetActorLocation()));
            Hash = HashCombine(Hash, GetTypeHash(Target->GetActorRotation().Quaternion()));
            Hash = HashCombine(Hash, GetTypeHash(Target->GetActorScale3D()));
        }
    }
    const bool bAnimatedUpdate = bRefreshAnimatedCasters && bEnableShadows && IsValid(KeyLight)
        && ShadowCasters.Num() > 0 && Targets.Num() > 0
        && SecondsSinceShadowUpdate >= 1.f / FMath::Clamp(ShadowUpdatesPerSecond, 1.f, 30.f);
    if (Hash != LastSceneHash || bAnimatedUpdate) { LastSceneHash = Hash; RefreshLighting(); }
    else BindLighting(); // Rebind newly rebuilt DMIs; color/intensity edits need no capture.
}

void AFurLightingController::RefreshLighting()
{
    SecondsSinceShadowUpdate = 0.f;
    bShadowValid = false;
    if (bEnableShadows && IsValid(KeyLight) && ShadowCasters.Num() > 0 && GetWorld())
    {
        FBox Bounds(ForceInit);
        for (AFurAuthoringActor* Target : Targets)
            if (IsValid(Target)) Bounds += Target->GetComponentsBoundingBox(true);
        if (Bounds.IsValid)
        {
            if (!ShadowDepth)
            {
                ShadowDepth = NewObject<UTextureRenderTarget2D>(this);
                ShadowDepth->RenderTargetFormat = RTF_R32f;
                ShadowDepth->ClearColor = FLinearColor(5000,0,0,0);
                ShadowDepth->InitAutoFormat(512,512);
                ShadowDepth->UpdateResourceImmediate(true);
            }
            ShadowCapture->TextureTarget = ShadowDepth;
            ShadowCapture->ShowOnlyActors = ShadowCasters;
            ShadowCapture->OrthoWidth = FMath::Clamp(ShadowWidth,50.f,2000.f);
            ShadowCapture->bUseCustomProjectionMatrix = true;
            ShadowCapture->CustomProjectionMatrix = FReversedZOrthoMatrix(
                ShadowCapture->OrthoWidth*.5,ShadowCapture->OrthoWidth*.5,1.0/5000.0,0);
            ShadowCapture->SetWorldLocationAndRotation(Bounds.GetCenter()-KeyLight->GetActorForwardVector()*1500,
                KeyLight->GetActorRotation());
            ShadowCapture->CaptureScene();
            ++ShadowCaptureCount;
            bShadowValid = true;
        }
    }
    BindLighting();
}

void AFurLightingController::SetEnvironment(UTextureCube* Cube, UTexture2D* BRDF, float Intensity)
{
    bOverrideEnvironment = true;
    bEnableEnvironment = true;
    EnvironmentCube = Cube;
    EnvironmentBRDF = BRDF;
    EnvironmentIntensity = FMath::Max(Intensity, 0.f);
    BindLighting();
}

void AFurLightingController::BindLighting()
{
    const UDirectionalLightComponent* Light = IsValid(KeyLight)
        ? Cast<UDirectionalLightComponent>(KeyLight->GetLightComponent()) : nullptr;
    const FVector Direction = Light ? -KeyLight->GetActorForwardVector() : FVector(0,0,1);
    FLinearColor Radiance = Light && Light->IsVisible() ? Light->GetLightColor()*(Light->Intensity/PI) : FLinearColor::Black;
    if (Light && Light->bUseTemperature) Radiance *= FLinearColor::MakeFromColorTemperature(Light->Temperature);
    // Resolve every bind so rotation, visibility, temperature and intensity edits
    // work without scheduling another depth capture. Never double-count a light.
    auto ResolveAdditional = [&](ADirectionalLight* Actor, ADirectionalLight* Other,
                                 FVector& OutDirection, FLinearColor& OutRadiance)
    {
        OutDirection = FVector(0,0,1);
        OutRadiance = FLinearColor::Black;
        if (!IsValid(Actor) || Actor == KeyLight.Get() || Actor == Other) return;
        const UDirectionalLightComponent* Component =
            Cast<UDirectionalLightComponent>(Actor->GetLightComponent());
        if (!Component || !Component->IsVisible() || Actor->IsHidden()) return;
        OutDirection = -Actor->GetActorForwardVector();
        OutRadiance = Component->GetLightColor() * (FMath::Max(Component->Intensity, 0.f) / PI);
        if (Component->bUseTemperature)
            OutRadiance *= FLinearColor::MakeFromColorTemperature(Component->Temperature);
    };
    FVector FillDirection, RimDirection;
    FLinearColor FillRadiance, RimRadiance;
    ResolveAdditional(FillLight.Get(), nullptr, FillDirection, FillRadiance);
    ResolveAdditional(RimLight.Get(), FillLight.Get(), RimDirection, RimRadiance);
    const bool bValidEnvironment = IsValid(EnvironmentCube) && IsValid(EnvironmentBRDF)
        && !EnvironmentCube->SRGB && !EnvironmentBRDF->SRGB
        && EnvironmentBRDF->AddressX == TA_Clamp && EnvironmentBRDF->AddressY == TA_Clamp;
    int32 SupportedMaterials = 0;
    int32 UnsupportedMaterials = 0;
    for (AFurAuthoringActor* Target : Targets)
    {
        if (!IsValid(Target)) continue;
        TInlineComponentArray<UPrimitiveComponent*> Components(Target);
        for (UPrimitiveComponent* Component : Components)
            for (int32 Slot=0; Slot<Component->GetNumMaterials(); ++Slot)
                if (UMaterialInstanceDynamic* Material=Cast<UMaterialInstanceDynamic>(Component->GetMaterial(Slot)))
                {
                    float PreviousIntensity = 0.f;
                    const bool bSupportsEnvironment = Material->GetScalarParameterValue(
                        FMaterialParameterInfo(TEXT("EnvironmentIntensity")), PreviousIntensity);
                    if (bSupportsEnvironment)
                    {
                        ++SupportedMaterials;
                        if (bOverrideEnvironment)
                        {
                            if (bValidEnvironment)
                            {
                                Material->SetTextureParameterValue(TEXT("FurEnvironment"), EnvironmentCube);
                                Material->SetTextureParameterValue(TEXT("FurEnvironmentBRDF"), EnvironmentBRDF);
                            }
                            Material->SetScalarParameterValue(TEXT("EnvironmentIntensity"),
                                bEnableEnvironment && bValidEnvironment ? FMath::Max(EnvironmentIntensity, 0.f) : 0.f);
                            Material->SetScalarParameterValue(TEXT("EnvironmentMaxMip"), FMath::Clamp(EnvironmentMaxMip, 0.f, 16.f));
                            Material->SetScalarParameterValue(TEXT("EnvironmentRecoveredAxes"), bEnvironmentRecoveredAxes ? 1.f : 0.f);
                        }
                        else if (bEnvironmentWasOverridden && Material->Parent)
                        {
                            // Only restore this controller's environment fields, never weather/shape.
                            for (const TCHAR* Name : {TEXT("EnvironmentIntensity"),TEXT("EnvironmentMaxMip"),TEXT("EnvironmentRecoveredAxes")})
                            {
                                float Value = 0.f;
                                if (Material->Parent->GetScalarParameterValue(FMaterialParameterInfo(Name), Value))
                                    Material->SetScalarParameterValue(Name, Value);
                            }
                            for (const TCHAR* Name : {TEXT("FurEnvironment"),TEXT("FurEnvironmentBRDF")})
                            {
                                UTexture* Value = nullptr;
                                if (Material->Parent->GetTextureParameterValue(FMaterialParameterInfo(Name), Value))
                                    Material->SetTextureParameterValue(Name, Value);
                            }
                        }
                    }
                    else ++UnsupportedMaterials;
                    auto Vector = [&](const TCHAR* Name,const FVector& Value)
                    { Material->SetVectorParameterValue(Name,FLinearColor(Value.X,Value.Y,Value.Z)); };
                    Vector(TEXT("SceneKeyDirection"),Direction);
                    Material->SetVectorParameterValue(TEXT("SceneKeyRadiance"),Radiance);
                    Vector(TEXT("SceneFillDirection"),FillDirection);
                    Vector(TEXT("SceneRimDirection"),RimDirection);
                    Material->SetVectorParameterValue(TEXT("SceneFillRadiance"),FillRadiance);
                    Material->SetVectorParameterValue(TEXT("SceneRimRadiance"),RimRadiance);
                    Material->SetScalarParameterValue(TEXT("SceneShadowEnabled"),bEnableShadows && bShadowValid ? 1.f:0.f);
                    Material->SetScalarParameterValue(TEXT("SceneShadowWidth"),ShadowCapture->OrthoWidth);
                    Material->SetScalarParameterValue(TEXT("SceneShadowBias"),ShadowBias);
                    Vector(TEXT("SceneShadowOrigin"),ShadowCapture->GetComponentLocation());
                    Vector(TEXT("SceneShadowForward"),ShadowCapture->GetForwardVector());
                    Vector(TEXT("SceneShadowRight"),ShadowCapture->GetRightVector());
                    Vector(TEXT("SceneShadowUp"),ShadowCapture->GetUpVector());
                    if (ShadowDepth) Material->SetTextureParameterValue(TEXT("SceneShadowDepth"),ShadowDepth);
                }
    }
    bEnvironmentWasOverridden = bOverrideEnvironment;
    if (!bOverrideEnvironment) EnvironmentStatus = TEXT("Using material environment settings.");
    else if (!bEnableEnvironment) EnvironmentStatus = TEXT("Environment disabled.");
    else if (!bValidEnvironment) EnvironmentStatus = TEXT("Assign a linear cube and linear clamp-addressed BRDF. Environment is disabled until valid.");
    else if (SupportedMaterials == 0) EnvironmentStatus = TEXT("No compatible target material. Create a scene-fur material with environment inputs first.");
    else if (UnsupportedMaterials > 0) EnvironmentStatus = TEXT("Environment applied; some target materials have no environment inputs.");
    else EnvironmentStatus = TEXT("Environment applied to target fur materials.");
}
