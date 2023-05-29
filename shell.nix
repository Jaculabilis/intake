{ pkgs ? import <nixpkgs> {} }:

let
  extraDeps = [
    pkgs.nixos-shell
    pkgs.python38Packages.black
    pkgs.python38Packages.pytest
  ];
  intake = import ./default.nix {
    inherit pkgs extraDeps;
  };
in intake
